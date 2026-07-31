#import "NativeMicroPythonRuntime.h"
#import <AVFoundation/AVFoundation.h>
#import <mach/mach_time.h>

#import "../../micropython-host/vs_ios_host/vs_ios_runtime.h"

static __weak NativeMicroPythonRuntime *activeRuntime;

@interface NativeMicroPythonRuntime ()
- (void)playAudioCommand:(NSString *)command;
@end

void vs_ios_runtime_log(const char *message) {
    // The embedded VM calls this hook around every evaluated tick.  Keep
    // exception/fatal diagnostics, but do not turn the 60 Hz loop into a
    // stream of NSLog calls on the simulator.
    if (message != NULL && (strncmp(message, "tick:", 5) == 0 || strncmp(message, "execute:", 8) == 0)) {
        return;
    }
    NSLog(@"Ventilastation VM: %s", message ?: "(null)");
}

void vs_ios_runtime_log_bytes(const char *message, size_t length) {
    NSString *text = [[NSString alloc] initWithBytes:message length:length encoding:NSUTF8StringEncoding] ?: @"(non-UTF8 diagnostics)";
    NSLog(@"Ventilastation Python: %@", text);
}

static void receiveCommand(const uint8_t *line, size_t lineLength, const uint8_t *payload, size_t payloadLength) {
    // The VM now runs on its own dedicated thread.  Keep UIKit, AVAudioPlayer,
    // and ObservableObject callbacks on the main queue instead of making the
    // game compete with SwiftUI's event loop.
    NSData *lineData = [NSData dataWithBytes:line length:lineLength];
    NSData *payloadData = [NSData dataWithBytes:payload length:payloadLength];
    dispatch_async(dispatch_get_main_queue(), ^{
        NativeMicroPythonRuntime *runtime = activeRuntime;
        if (runtime == nil) return;
        NSString *command = [[NSString alloc] initWithData:lineData encoding:NSUTF8StringEncoding] ?: @"(binary command)";
        if ([command hasPrefix:@"traceback"]) {
            NSString *details = [[NSString alloc] initWithData:payloadData encoding:NSUTF8StringEncoding] ?: @"(binary traceback)";
            NSLog(@"Ventilastation Python traceback: %@", details);
        }
        if ([command hasPrefix:@"music"] || [command hasPrefix:@"sound"]) {
            [runtime playAudioCommand:command];
        }
        if (runtime.commandHandler != nil) {
            runtime.commandHandler(lineData, payloadData);
        }
    });
}

static void receiveFrame(const uint8_t *sprites, size_t spritesLength, const uint8_t *metadata, size_t metadataLength) {
    NSData *spritesData = [NSData dataWithBytes:sprites length:spritesLength];
    NSData *metadataData = [NSData dataWithBytes:metadata length:metadataLength];
    dispatch_async(dispatch_get_main_queue(), ^{
        NativeMicroPythonRuntime *runtime = activeRuntime;
        if (runtime.frameHandler != nil) {
            runtime.frameHandler(spritesData, metadataData);
        }
    });
}

@implementation NativeMicroPythonRuntime {
    BOOL _running;
    NSString *_lastError;
    NSString *_runtimeRoot;
    AVAudioPlayer *_musicPlayer;
    AVAudioPlayer *_soundPlayer;
    NSThread *_tickThread;
    BOOL _tickStopRequested;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _lastError = @"";
    }
    return self;
}

- (BOOL)isRunning {
    @synchronized (self) {
        return _running;
    }
}

- (NSString *)lastError {
    return _lastError;
}

- (BOOL)startAtRuntimeRoot:(NSString *)runtimeRoot {
    _runtimeRoot = [runtimeRoot copy];
    activeRuntime = self;
    NSLog(@"Ventilastation: starting MicroPython at %@", runtimeRoot);
    vs_ios_host_callbacks_t callbacks = {
        .command = receiveCommand,
        .present = receiveFrame,
    };
    // MicroPython's conservative GC records the stack boundary of the thread
    // that starts the VM.  Use one dedicated NSThread for both startup and all
    // ticks; a GCD queue may migrate work between worker-thread stacks.
    __block BOOL started = NO;
    dispatch_semaphore_t startup = dispatch_semaphore_create(0);
    NSString *rootCopy = [runtimeRoot copy];
    _tickStopRequested = NO;
    __weak NativeMicroPythonRuntime *weakSelf = self;
    _tickThread = [[NSThread alloc] initWithBlock:^{
        @autoreleasepool {
            NativeMicroPythonRuntime *runtime = weakSelf;
            if (runtime == nil) {
                dispatch_semaphore_signal(startup);
                return;
            }
            started = vs_ios_runtime_start(rootCopy.fileSystemRepresentation, &callbacks);
            @synchronized (runtime) {
                runtime->_running = started;
            }
            dispatch_semaphore_signal(startup);
            mach_timebase_info_data_t timebase;
            mach_timebase_info(&timebase);
            const uint64_t tickInterval = (30000000ULL * timebase.denom) / timebase.numer;
            uint64_t nextTick = mach_absolute_time();
            while (started) {
                @autoreleasepool {
                    @synchronized (runtime) {
                        if (runtime->_tickStopRequested) break;
                    }
                    if (!vs_ios_runtime_tick()) {
                        @synchronized (runtime) {
                            runtime->_running = NO;
                        }
                        break;
                    }
                }
                // director.run() schedules its real hardware loop every
                // 30 ms.  browser.tick() is the one-step form of that loop,
                // so use an absolute deadline rather than sleeping 30 ms
                // after the tick (which would add the tick duration again).
                nextTick += tickInterval;
                mach_wait_until(nextTick);
            }
        }
    }];
    _tickThread.qualityOfService = NSQualityOfServiceUserInteractive;
    [_tickThread start];
    dispatch_semaphore_wait(startup, DISPATCH_TIME_FOREVER);
    _running = started;
    NSLog(@"Ventilastation: MicroPython start returned %d", _running);
    if (!_running) {
        _lastError = [NSString stringWithUTF8String:vs_ios_runtime_last_error() ?: "MicroPython startup failed"];
    }
    return _running;
}

- (void)startTickLoop {
    // The dedicated thread starts ticking immediately after VM startup.
}

- (void)stopTickLoop {
    @synchronized (self) {
        _tickStopRequested = YES;
    }
}

- (void)playAudioCommand:(NSString *)command {
    NSArray<NSString *> *parts = [command componentsSeparatedByString:@" "];
    if (parts.count < 2) return;
    if ([parts[0] isEqualToString:@"music"] && [parts[1] isEqualToString:@"off"]) {
        [_musicPlayer stop];
        _musicPlayer = nil;
        return;
    }
    NSString *qualifiedName = parts[1];
    NSRange slash = [qualifiedName rangeOfString:@"/"];
    NSString *slug = slash.location == NSNotFound ? nil : [qualifiedName substringToIndex:slash.location];
    NSString *name = slash.location == NSNotFound ? qualifiedName : [qualifiedName substringFromIndex:slash.location + 1];
    NSMutableArray<NSString *> *directories = [NSMutableArray array];
    if (slug.length > 0) {
        NSString *slugPath = [slug stringByReplacingOccurrencesOfString:@"." withString:@"/"];
        [directories addObject:[_runtimeRoot stringByAppendingPathComponent:[NSString stringWithFormat:@"games/%@/sounds", slugPath]]];
        [directories addObject:[_runtimeRoot stringByAppendingPathComponent:[NSString stringWithFormat:@"system/%@/sounds", slugPath]]];
    }
    // Unqualified legacy commands have historically resolved against the
    // current Vyruss game. Keep that fallback while qualified V2 commands use
    // the originating game's own sounds directory (e.g. alecu.vixeous).
    [directories addObject:[_runtimeRoot stringByAppendingPathComponent:@"games/alecu/vyruss_vs2/sounds"]];
    [directories addObject:[_runtimeRoot stringByAppendingPathComponent:@"games/alecu/vixeous/sounds"]];
    NSURL *url = nil;
    for (NSString *directory in directories) {
        for (NSString *extension in @[@"wav", @"mp3", @"ogg"]) {
            NSString *candidatePath = [directory stringByAppendingPathComponent:name];
            if ([[candidatePath pathExtension] length] == 0) {
                candidatePath = [candidatePath stringByAppendingPathExtension:extension];
            }
            NSURL *candidate = [NSURL fileURLWithPath:candidatePath];
            if ([[NSFileManager defaultManager] fileExistsAtPath:candidate.path]) { url = candidate; break; }
        }
        if (url != nil) break;
    }
    if (url == nil) return;
    NSError *error = nil;
    AVAudioPlayer *player = [[AVAudioPlayer alloc] initWithContentsOfURL:url error:&error];
    if (player == nil) return;
    player.numberOfLoops = ([parts[0] isEqualToString:@"music"] && parts.count > 2 && [parts[2] isEqualToString:@"loop"]) ? -1 : 0;
    [player prepareToPlay];
    [player play];
    if ([parts[0] isEqualToString:@"music"]) _musicPlayer = player;
    else _soundPlayer = player;
}

- (BOOL)tick {
    if (!_running) {
        return NO;
    }
    _running = vs_ios_runtime_tick();
    if (!_running) {
        _lastError = [NSString stringWithUTF8String:vs_ios_runtime_last_error() ?: "MicroPython frame failed"];
    }
    return _running;
}

- (void)dealloc {
    [self stopTickLoop];
}

- (void)setJoy1:(uint8_t)joy1 joy2:(uint8_t)joy2 extra:(uint8_t)extra exitRequested:(BOOL)exitRequested {
    static uint8_t previousJoy1 = 0xff;
    static uint8_t previousJoy2 = 0xff;
    static uint8_t previousExtra = 0xff;
    if (joy1 != previousJoy1 || joy2 != previousJoy2 || extra != previousExtra || exitRequested) {
        NSLog(@"Ventilastation runtime input joy1=%02x joy2=%02x extra=%02x exit=%@", joy1, joy2, extra, exitRequested ? @"YES" : @"NO");
        previousJoy1 = joy1;
        previousJoy2 = joy2;
        previousExtra = extra;
    }
    vs_ios_runtime_set_input(joy1, joy2, extra, exitRequested);
}

@end
