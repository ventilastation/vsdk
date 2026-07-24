// See hall_filter.h for the API contract (portable, host-testable, not
// ISR-safe). A gated nearest-neighbor predictor, not a smoothed one: period_us
// always snaps to the most recent trustworthy single-revolution measurement
// (or elapsed/n on a recovered missed-pulse gap), never blended with older
// samples. Only jitter_us -- a magnitude-only statistic used solely to size
// the classification gate, never fed into rendering -- is smoothed.
//
// This is deliberate, not an oversight: an earlier version smoothed period_us
// too (an alpha-beta / g-h filter, the steady-state form a Kalman filter
// collapses to for this constant-velocity system). On real hardware that
// smoothing showed up as a visible image wobble -- gpu_serve() divides by
// period_us every column to interpolate position between hall edges, so any
// lag between the smoothed estimate and the disc's actual instantaneous
// period (which does vary a little revolution to revolution: motor cogging,
// blade/bearing dynamics, air turbulence -- normal, not a fault) warps that
// revolution's image slightly, snapping back into alignment at the next real
// edge. A fresh single-revolution measurement is a *better* predictor of the
// immediate next revolution than a multi-revolution average anyway (nearby
// revolutions correlate more than distant ones), so removing the smoothing
// fixed the wobble without giving up the gating: a bad edge (spurious/missed/
// outlier/stall) is rejected or reconstructed *before* it ever reaches the
// update at the bottom of this function, so period_us only ever absorbs
// values the gate already judged trustworthy.
//
// Classification per incoming edge, relative to the last ACCEPTED edge:
//   1. n = round(elapsed / period_us) -- nearest integer count of revolutions
//      since the last accepted edge.
//   2. If elapsed is meaningfully less than one period AND doesn't fit the
//      jitter gate: SPURIOUS. Reject outright -- don't move last_turn_us, so
//      the *next* real edge is still judged against the true last revolution,
//      not the bounce. (Accepting an early edge would run the phase estimate
//      backwards relative to the physical disc.)
//   3. If it fits n periods within the jitter gate: normal accept (n==1) or
//      MISSED-pulse accept (n>1) -- either way, period_us becomes elapsed/n
//      (the per-revolution estimate), not raw elapsed, so a missed pulse
//      doesn't get misread as the fan slowing to half speed.
//   4. Otherwise (a late arrival that doesn't cleanly fit any nearby integer):
//      OUTLIER. Accept the position (so phase can't permanently drift out of
//      sync) but don't trust it to update period_us/jitter_us.
//   5. A gap beyond HALL_FILTER_MAX_PLAUSIBLE_N periods isn't "a few missed
//      pulses" anymore -- treat it as a stop/restart: reseed the position
//      without touching the period/jitter estimate, and let the next ordinary
//      n==1 pulse reconverge it immediately (no lag to recover from).
//
// Cases 2/4/5 above are all "this edge doesn't fit period_us" -- reasonable
// when period_us is basically right and the edge is a one-off (real sensor
// noise, a single skipped edge). But period_us itself can simply be WRONG:
// hall_filter_init() seeds it with a fixed guess (there's no real revolution
// to measure yet), so at every cold start the fan spins up from 0 RPM through
// a rapidly-shrinking period while the filter is still anchored to that
// guess -- and the same can happen mid-session if the fan stops and restarts
// at a different speed. In both cases EVERY edge for a while looks like it
// "doesn't fit", each interpreted via case 3 as elapsed/n -- which quietly
// divides the true (still-slow) revolution time by n, so gpu_serve() (which
// divides by period_us every column) laps the physical disc n times within
// one real turn. That's the reported "drawing all columns several times in
// the same turn" during spin-up.
//
// disagreement_streak tells the two situations apart: real sensor noise is
// an isolated blip (the very next edge fits again), while a genuinely wrong
// period_us keeps producing edges that don't fit, over and over. Once
// HALL_FILTER_RESYNC_STREAK edges in a row fail to fit cleanly (whichever of
// cases 2/4/5 each individually landed in), that's no longer noise -- trust
// this edge outright as ground truth (period_us = raw elapsed, jitter_us
// reset) rather than keep reinterpreting a real, sustained speed change
// through a model that assumes period_us is approximately right.
//
// All arithmetic is integer/fixed-point (no floats, no libm) so behavior is
// identical on-device and in the host test.

#include "hall_filter.h"

#define HALL_FILTER_BETA_SHIFT 2       // jitter smoothing gain: 1/4 per accepted sample
#define HALL_FILTER_GATE_K 5           // gate width, in multiples of tracked jitter
#define HALL_FILTER_MIN_GATE_DEN 8     // gate floor: period_us / 8 (~12.5%), for before jitter has warmed up
#define HALL_FILTER_MAX_PLAUSIBLE_N 8  // beyond this many implied periods, treat as a stall/restart
#define HALL_FILTER_RESYNC_STREAK 2    // consecutive non-fitting edges before trusting a new period outright

static int64_t abs64(int64_t v) {
    return v < 0 ? -v : v;
}

void hall_filter_init(hall_filter_t* f, int64_t initial_period_us) {
    f->last_turn_us = 0;
    f->period_us = initial_period_us > 0 ? initial_period_us : 1;
    f->jitter_us = 0;
    f->initialized = false;
    f->disagreement_streak = 0;
    f->accepted_count = 0;
    f->spurious_count = 0;
    f->missed_count = 0;
    f->missed_pulses_total = 0;
    f->outlier_count = 0;
    f->stall_count = 0;
    f->resync_count = 0;
}

static bool hall_filter_resync(hall_filter_t* f, int64_t this_turn_us, int64_t elapsed) {
    if (++f->disagreement_streak < HALL_FILTER_RESYNC_STREAK) {
        return false;
    }
    f->last_turn_us = this_turn_us;
    f->period_us = elapsed;
    f->jitter_us = 0;
    f->disagreement_streak = 0;
    f->accepted_count++;
    f->resync_count++;
    return true;
}

bool hall_filter_submit(hall_filter_t* f, int64_t this_turn_us) {
    if (!f->initialized) {
        f->last_turn_us = this_turn_us;
        f->initialized = true;
        f->disagreement_streak = 0;
        f->accepted_count++;
        return true;
    }

    int64_t elapsed = this_turn_us - f->last_turn_us;
    if (elapsed <= 0 || f->period_us <= 0) {
        // Non-monotonic timestamp or a broken filter state -- reseed rather
        // than divide by a non-positive period.
        f->last_turn_us = this_turn_us;
        f->stall_count++;
        return true;
    }

    if (f->accepted_count <= 1) {
        // This is the first real edge since hall_filter_init()'s seed -- no
        // revolution has ever actually been measured yet, so there's no basis
        // to trust an n-multiple hypothesis against a plain guess. Trust this
        // edge outright rather than risk it coincidentally landing near an
        // exact multiple of the guess (which would corrupt period_us on the
        // very first sample, before disagreement_streak has any history to
        // react to).
        f->last_turn_us = this_turn_us;
        f->period_us = elapsed;
        f->jitter_us = 0;
        f->disagreement_streak = 0;
        f->accepted_count++;
        return true;
    }

    int64_t n = (elapsed + f->period_us / 2) / f->period_us;
    if (n < 1) {
        n = 1;
    }

    if (n > HALL_FILTER_MAX_PLAUSIBLE_N) {
        if (hall_filter_resync(f, this_turn_us, elapsed)) {
            return true;
        }
        f->last_turn_us = this_turn_us;
        f->stall_count++;
        return true;
    }

    int64_t gate_floor = f->period_us / HALL_FILTER_MIN_GATE_DEN;
    int64_t gate = HALL_FILTER_GATE_K * f->jitter_us;
    if (gate < gate_floor) {
        gate = gate_floor;
    }

    int64_t predicted = n * f->period_us;
    int64_t residual = elapsed - predicted;
    int64_t abs_residual = abs64(residual);

    if (abs_residual >= gate) {
        // A real spinning disc has inertia: RPM can't double revolution to
        // revolution, even in an aggressive spin-up (confirmed against the
        // reported bug's own repro -- a much looser "less than one gate
        // width short of period_us" threshold flagged nearly every edge of a
        // realistic acceleration ramp as "too early", rejecting each without
        // moving last_turn_us, which quietly merged pairs of real revolutions
        // into one inflated sample). So only an edge implying at least that
        // large a jump is treated as a bounce candidate; anything less is a
        // plausible real (if unmodeled) revolution and falls through to the
        // outlier-accept path below, which still moves last_turn_us.
        bool too_early = elapsed < f->period_us / 2;
        bool isolated = f->disagreement_streak == 0;
        if (hall_filter_resync(f, this_turn_us, elapsed)) {
            return true;
        }
        if (too_early && isolated) {
            // An early arrival with no recent history of trouble -- most
            // likely a bounce that snuck past the caller's absolute debounce
            // floor. Reject outright: don't move last_turn_us, so the next
            // edge is still judged against the true last revolution.
            f->spurious_count++;
            return false;
        }
        // Already mid-streak (recent edges haven't fit either) or a late
        // rather than early arrival: accept the position. This keeps each
        // subsequent elapsed a single real inter-edge gap instead of several
        // summed across a rejected edge, so if this is sustained acceleration
        // rather than one bounce, the streak's eventual resync (above) reads
        // an accurate one-revolution sample instead of an inflated one.
        f->last_turn_us = this_turn_us;
        f->outlier_count++;
        return true;
    }

    int64_t sample_period = elapsed / n;
    int64_t sample_jitter = abs_residual / n;
    f->last_turn_us = this_turn_us;
    f->period_us = sample_period;
    f->jitter_us += (sample_jitter - f->jitter_us) >> HALL_FILTER_BETA_SHIFT;
    f->disagreement_streak = 0;
    f->accepted_count++;
    if (n > 1) {
        f->missed_count++;
        f->missed_pulses_total += (uint32_t)(n - 1);
    }
    return true;
}
