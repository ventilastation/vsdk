#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface NativeMicroPythonRuntime : NSObject

@property (nonatomic, copy, nullable) void (^commandHandler)(NSData *line, NSData *payload);
@property (nonatomic, copy, nullable) void (^frameHandler)(NSData *sprites, NSData *metadata);
@property (nonatomic, readonly, getter=isRunning) BOOL running;
@property (nonatomic, readonly) NSString *lastError;

- (BOOL)startAtRuntimeRoot:(NSString *)runtimeRoot;
- (void)startTickLoop;
- (void)stopTickLoop;
- (BOOL)tick;
- (void)setJoy1:(uint8_t)joy1 joy2:(uint8_t)joy2 extra:(uint8_t)extra exitRequested:(BOOL)exitRequested;

@end

NS_ASSUME_NONNULL_END
