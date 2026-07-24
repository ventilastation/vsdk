/* Host tests for the hall-pulse filter shared by the MicroPython POV
 * renderer (povdisplay.c) and the native retro-go POV driver
 * (ventilastation_pov.c). Feeds synthetic edge sequences and checks the
 * classification (normal / spurious / missed / outlier / stall) and the
 * resulting period_us, matching the model documented in hall_filter.c.
 */
#include <stddef.h>
#include <stdio.h>

#include "hall_filter.h"

static int failures = 0;

#define CHECK(condition, message) \
    do { \
        if (!(condition)) { \
            printf("FAIL %s\n", message); \
            failures++; \
        } \
    } while (0)

#define PERIOD 40000  /* 40ms/revolution -- an arbitrary, plausible fan speed */

static void test_first_edge_always_accepted(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    CHECK(hall_filter_submit(&f, 1000000), "first edge is accepted");
    CHECK(f.last_turn_us == 1000000, "first edge seeds last_turn_us");
    CHECK(f.accepted_count == 1, "first edge counts as accepted");
    CHECK(f.spurious_count == 0 && f.missed_count == 0 && f.outlier_count == 0
        && f.stall_count == 0, "first edge touches no other counter");
}

static void test_steady_spin_converges_and_stays_quiet(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 50; i++) {
        t += PERIOD;
        CHECK(hall_filter_submit(&f, t), "steady pulse is accepted");
    }
    CHECK(f.accepted_count == 51, "all steady pulses accepted");
    CHECK(f.spurious_count == 0, "steady spin flags no spurious pulses");
    CHECK(f.missed_count == 0, "steady spin flags no missed pulses");
    CHECK(f.outlier_count == 0, "steady spin flags no outliers");
    CHECK(f.stall_count == 0, "steady spin flags no stalls");
    CHECK(f.period_us == PERIOD, "period estimate stays put when already correct");
    CHECK(f.last_turn_us == t, "last_turn_us tracks the latest accepted edge");
}

static void test_gradual_spinup_is_not_flagged(void) {
    /* Linearly ramp the period down 40ms -> ~32ms over 40 revolutions (a 20%
     * speed-up, much slower than the per-revolution jitter gate) -- legitimate
     * spin-up must never trip spurious/missed/outlier. */
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    int64_t period = PERIOD;
    for (int i = 0; i < 40; i++) {
        period -= period / 50;  /* ~2%/revolution */
        t += period;
        CHECK(hall_filter_submit(&f, t), "spin-up pulse is accepted");
    }
    CHECK(f.spurious_count == 0, "gradual spin-up flags no spurious pulses");
    CHECK(f.missed_count == 0, "gradual spin-up flags no missed pulses");
    CHECK(f.outlier_count == 0, "gradual spin-up flags no outliers");
    CHECK(f.period_us == period,
        "period estimate tracks the latest measurement with no smoothing lag");
}

static void test_period_and_phase_both_track_with_zero_lag(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }
    CHECK(f.period_us == PERIOD, "period stable before the step change");

    /* A single modest, legitimate step (5% faster) -- well inside the gate
     * (the gate floor alone is period/8, ~12.5%) -- must be reflected
     * exactly on the very next sample, not blended in gradually: neither the
     * turn duration (period_us) nor the turn start (last_turn_us, the phase
     * reference) are damped once an edge passes the gate. Only the jitter
     * estimate used to size that gate is smoothed. */
    int64_t new_period = PERIOD - PERIOD / 20;
    t += new_period;
    CHECK(hall_filter_submit(&f, t), "a modest step change is accepted");
    CHECK(f.period_us == new_period,
        "period snaps to the new measurement immediately -- no smoothing lag");
    CHECK(f.last_turn_us == t,
        "the turn start (phase) always snaps to the raw edge, filtered or not");
}

static void test_spurious_bounce_is_rejected_and_does_not_move_phase(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }
    int64_t last_good = f.last_turn_us;
    int64_t period_before = f.period_us;

    /* A bounce 30% of the way into the next revolution -- clearly too early
     * to be a real edge, but past the caller's absolute debounce floor. */
    int64_t bounce = last_good + (PERIOD * 3) / 10;
    CHECK(!hall_filter_submit(&f, bounce), "early bounce is rejected");
    CHECK(f.spurious_count == 1, "bounce increments spurious_count");
    CHECK(f.last_turn_us == last_good, "rejected bounce does not move last_turn_us");
    CHECK(f.period_us == period_before, "rejected bounce does not disturb period_us");

    /* The next REAL pulse, still measured from the last good edge (not the
     * bounce), must be accepted normally. */
    t = last_good + PERIOD;
    CHECK(hall_filter_submit(&f, t), "real pulse after a bounce is accepted");
    CHECK(f.last_turn_us == t, "real pulse after a bounce updates last_turn_us");
}

static void test_one_missed_pulse_is_absorbed(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }

    t += 2 * PERIOD;  /* one revolution's edge never arrived */
    CHECK(hall_filter_submit(&f, t), "edge after a missed pulse is accepted");
    CHECK(f.missed_count == 1, "one missed-pulse event recorded");
    CHECK(f.missed_pulses_total == 1, "exactly one skipped edge counted");
    CHECK(f.spurious_count == 0 && f.outlier_count == 0 && f.stall_count == 0,
        "a missed pulse is not also flagged as spurious/outlier/stall");
    CHECK(f.period_us == PERIOD,
        "period estimate is recovered from elapsed/n, not corrupted toward 2x");
}

static void test_multiple_missed_pulses_are_counted(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }

    t += 4 * PERIOD;  /* three consecutive revolutions' edges never arrived */
    CHECK(hall_filter_submit(&f, t), "edge after several missed pulses is accepted");
    CHECK(f.missed_count == 1, "still a single missed-pulse event");
    CHECK(f.missed_pulses_total == 3, "three skipped edges counted");
    CHECK(f.period_us == PERIOD, "period estimate survives multiple missed pulses");
}

static void test_outlier_moves_phase_but_not_period(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }
    int64_t period_before = f.period_us;

    /* 2.5 periods -- doesn't cleanly fit n=2 or n=3 within the jitter gate. */
    t += (PERIOD * 5) / 2;
    CHECK(hall_filter_submit(&f, t), "an unclassifiable gap is still accepted (phase)");
    CHECK(f.outlier_count == 1, "unclassifiable gap counted as an outlier");
    CHECK(f.missed_count == 0, "an outlier is not double-counted as missed");
    CHECK(f.last_turn_us == t, "outlier acceptance still moves last_turn_us");
    CHECK(f.period_us == period_before, "outlier does not disturb the period estimate");
}

static void test_large_gap_is_a_stall_not_dozens_of_missed_pulses(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }
    int64_t period_before = f.period_us;

    t += 20 * PERIOD;  /* the fan stopped and restarted, not "19 missed pulses" */
    CHECK(hall_filter_submit(&f, t), "restart edge is accepted");
    CHECK(f.stall_count == 1, "an implausibly large gap is flagged as a stall");
    CHECK(f.missed_count == 0 && f.missed_pulses_total == 0,
        "a stall is not miscounted as a pile of missed pulses");
    CHECK(f.last_turn_us == t, "stall acceptance still moves last_turn_us");
    CHECK(f.period_us == period_before, "stall does not disturb the period estimate");

    /* Normal pulses resume cleanly afterward. */
    t += PERIOD;
    CHECK(hall_filter_submit(&f, t), "pulse after a stall is accepted normally");
    CHECK(f.stall_count == 1, "no further stalls once cadence resumes");
}

static void test_spinup_from_zero_rpm_does_not_lap_the_disc(void) {
    /* Mirrors a real cold start: hall_filter_init() seeds a fixed guess (1s,
     * matching the MicroPython default) with no real revolution behind it
     * yet, then the fan accelerates from a stop through a rapidly shrinking
     * period down to a steady 100ms cruise. Each of the early, still-slow
     * turns is many times longer than the assumed 1s guess would predict for
     * whatever count of "missed" edges it implies -- the reported bug was
     * exactly this: period_us collapsing to a small fraction of the real
     * (still slow) turn, so gpu_serve() (which divides by period_us every
     * column) redraws all 256 columns several times within one real turn. */
    hall_filter_t f;
    hall_filter_init(&f, 1000000);
    int64_t t = 0;
    hall_filter_submit(&f, t);

    int64_t true_periods[] = {
        4000000, 2600000, 1700000, 1100000, 700000,
        450000, 290000, 190000, 130000, 105000,
        100000, 100000, 100000, 100000, 100000,
    };
    for (size_t i = 0; i < sizeof(true_periods) / sizeof(true_periods[0]); i++) {
        t += true_periods[i];
        CHECK(hall_filter_submit(&f, t), "spin-up edge is accepted");
        CHECK(f.period_us * 3 >= true_periods[i],
            "period estimate never collapses to a small fraction of the real turn");
    }
    CHECK(f.period_us < 200000, "period estimate has caught up to the steady 100ms cruise speed");
    CHECK(f.resync_count > 0, "sustained disagreement during spin-up actually triggered a resync");
}

static void test_stop_and_restart_faster_resyncs_within_a_few_edges(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    int64_t t = 0;
    hall_filter_submit(&f, t);
    for (int i = 0; i < 5; i++) {
        t += PERIOD;
        hall_filter_submit(&f, t);
    }

    /* The motor stops, then restarts at a much faster steady speed (a
     * quarter of the original period) -- not something a toggle would be
     * cycled for in the field, so this has to self-correct. */
    t += 20 * PERIOD;
    hall_filter_submit(&f, t);
    CHECK(f.stall_count >= 1, "the stop itself is recognized as a stall, not dozens of missed pulses");

    int64_t new_period = PERIOD / 4;
    int edges_to_resync = -1;
    for (int i = 0; i < 10; i++) {
        t += new_period;
        hall_filter_submit(&f, t);
        if (f.period_us * 3 <= new_period * 4 && f.period_us * 4 >= new_period * 3) {
            edges_to_resync = i + 1;
            break;
        }
    }
    CHECK(edges_to_resync > 0 && edges_to_resync <= 3,
        "restarting at a different speed re-anchors within a few edges, not indefinitely");
}

static void test_non_monotonic_timestamp_reseeds_without_crashing(void) {
    hall_filter_t f;
    hall_filter_init(&f, PERIOD);
    hall_filter_submit(&f, 1000000);
    CHECK(hall_filter_submit(&f, 999999), "a backward timestamp is handled, not fatal");
    CHECK(f.stall_count == 1, "a non-monotonic timestamp is counted as a stall");
    CHECK(f.last_turn_us == 999999, "state reseeds to the new (backward) timestamp");
}

int main(void) {
    test_first_edge_always_accepted();
    test_steady_spin_converges_and_stays_quiet();
    test_gradual_spinup_is_not_flagged();
    test_period_and_phase_both_track_with_zero_lag();
    test_spurious_bounce_is_rejected_and_does_not_move_phase();
    test_one_missed_pulse_is_absorbed();
    test_multiple_missed_pulses_are_counted();
    test_outlier_moves_phase_but_not_period();
    test_large_gap_is_a_stall_not_dozens_of_missed_pulses();
    test_spinup_from_zero_rpm_does_not_lap_the_disc();
    test_stop_and_restart_faster_resyncs_within_a_few_edges();
    test_non_monotonic_timestamp_reseeds_without_crashing();

    if (failures) {
        return 1;
    }
    printf("hall filter host tests passed\n");
    return 0;
}
