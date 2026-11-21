// YozoraCompat.m - runtime compatibility patch for Yozora's native YZPageView
// Built separately and embedded in the ARM64 TrollStore IPA.
// No network access, credentials, or clipboard data are logged or transmitted.
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <mach/mach.h>
#import <stdint.h>

static char YZPasteToolbarKey;
static IMP YZOriginalLongPress = NULL;
static IMP YZInheritedCanPerform = NULL;

static int YZFocusedInputKind(id view) {
    Ivar input = class_getInstanceVariable(objc_getClass("YZPageView"), "_inputKind");
    if (!input) return 0;
    return *(int *)((uint8_t *)(__bridge void *)view + ivar_getOffset(input));
}

static void YZPaste(id self, SEL cmd, id sender) {
    (void)cmd; (void)sender;
    if (![self isFirstResponder] || YZFocusedInputKind(self) == 0) return;
    // Read only in response to an explicit tap: avoids clipboard access during menus.
    NSString *clipboard = [UIPasteboard generalPasteboard].string;
    if (![clipboard length]) return;
    SEL insert = @selector(insertText:);
    if ([self respondsToSelector:insert]) {
        ((void (*)(id, SEL, id))[self methodForSelector:insert])(self, insert, clipboard);
    }
}

static BOOL YZCanPerform(id self, SEL cmd, SEL action, id sender) {
    (void)cmd;
    if (action == @selector(paste:))
        return [self isFirstResponder] &&
            YZFocusedInputKind(self) != 0 &&
            [UIPasteboard generalPasteboard].hasStrings;
    if (YZInheritedCanPerform)
        return ((BOOL (*)(id, SEL, SEL, id))YZInheritedCanPerform)(self, cmd, action, sender);
    return NO;
}

static UIView *YZInputAccessory(id self, SEL cmd) {
    (void)cmd;
    UIView *toolbar = objc_getAssociatedObject(self, &YZPasteToolbarKey);
    if (toolbar) return toolbar;
    toolbar = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 320, 43)];
    toolbar.backgroundColor = [UIColor colorWithWhite:0.92 alpha:1];
    toolbar.autoresizingMask = UIViewAutoresizingFlexibleWidth;

    UIButton *paste = [UIButton buttonWithType:UIButtonTypeSystem];
    paste.frame = CGRectMake(10, 3, 84, 37);
    paste.autoresizingMask = UIViewAutoresizingFlexibleRightMargin;
    [paste setTitle:@"Paste" forState:UIControlStateNormal];
    [paste addTarget:self action:@selector(paste:) forControlEvents:UIControlEventTouchUpInside];
    [toolbar addSubview:paste];

    UILabel *hint = [[UILabel alloc] initWithFrame:CGRectMake(106, 5, 205, 33)];
    hint.text = @"Yozora keyboard";
    hint.font = [UIFont systemFontOfSize:12];
    hint.textColor = [UIColor darkGrayColor];
    hint.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    [toolbar addSubview:hint];

    objc_setAssociatedObject(self, &YZPasteToolbarKey, toolbar, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return toolbar;
}

static void YZLongPress(id self, SEL cmd, UILongPressGestureRecognizer *gesture) {
    // On password fields, normal Yozora selection owns the edit menu but never
    // offers Paste. Show Paste from the actual keyboard responder instead.
    if ([self isFirstResponder] && YZFocusedInputKind(self) == 3) {
        if (gesture.state == UIGestureRecognizerStateBegan) {
            [self becomeFirstResponder];
            CGPoint point = [gesture locationInView:self];
            UIMenuController *menu = [UIMenuController sharedMenuController];
            [menu setTargetRect:CGRectMake(point.x - 10, point.y - 10, 20, 20) inView:self];
            [menu setMenuVisible:YES animated:YES];
        }
        return;
    }
    if (YZOriginalLongPress)
        ((void (*)(id, SEL, id))YZOriginalLongPress)(self, cmd, gesture);
}

static uint64_t YZMemoryFootprint(void) {
    task_vm_info_data_t info = {0};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    kern_return_t kr = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count);
    return kr == KERN_SUCCESS ? info.phys_footprint : 0;
}

@interface YZCompatMonitor : NSObject
@property (nonatomic, assign) NSTimeInterval lastCleanup;
+ (instancetype)shared;
- (void)checkMemory:(NSTimer *)timer;
@end
@implementation YZCompatMonitor
+ (instancetype)shared {
    static YZCompatMonitor *monitor;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ monitor = [[self alloc] init]; });
    return monitor;
}
- (void)checkMemory:(NSTimer *)timer {
    (void)timer;
    UIApplication *application = [UIApplication sharedApplication];
    if (application.applicationState != UIApplicationStateActive) return;
    uint64_t used = YZMemoryFootprint();
    if (!used || used < 650ULL * 1024ULL * 1024ULL) return;
    NSTimeInterval now = [[NSDate date] timeIntervalSince1970];
    if (now - self.lastCleanup < 25) return;
    UIViewController *controller = application.keyWindow.rootViewController;
    if (!controller || ![NSStringFromClass([controller class]) isEqualToString:@"YZBrowserController"])
        return;
    self.lastCleanup = now;
    NSLog(@"YozoraCompat: high memory %.0f MiB, requesting existing Yozora cache cleanup", used / 1048576.0);
    // Yozora already implements this method: discards suspended tab cores and
    // invokes yozora_release_memory_async(). Do not touch the engine directly.
    [controller didReceiveMemoryWarning];
}
@end

static void YZInstallHooks(void) {
    Class page = objc_getClass("YZPageView");
    if (!page) {
        NSLog(@"YozoraCompat: YZPageView unavailable, no patch installed");
        return;
    }
    Method parentCanPerform = class_getInstanceMethod(class_getSuperclass(page), @selector(canPerformAction:withSender:));
    YZInheritedCanPerform = parentCanPerform ? method_getImplementation(parentCanPerform) : NULL;
    class_addMethod(page, @selector(paste:), (IMP)YZPaste, "v@:@");
    class_addMethod(page, @selector(canPerformAction:withSender:), (IMP)YZCanPerform, "c@::@");
    class_addMethod(page, @selector(inputAccessoryView), (IMP)YZInputAccessory, "@@:");
    Method longPress = class_getInstanceMethod(page, @selector(longPress:));
    if (longPress)
        YZOriginalLongPress = method_setImplementation(longPress, (IMP)YZLongPress);
    NSLog(@"YozoraCompat: paste menu and keyboard button installed");
}

@interface YZCompatBootstrap : NSObject
@end
@implementation YZCompatBootstrap
+ (void)load {
    YZInstallHooks();
    dispatch_async(dispatch_get_main_queue(), ^{
        [NSTimer scheduledTimerWithTimeInterval:8.0
                                         target:[YZCompatMonitor shared]
                                       selector:@selector(checkMemory:)
                                       userInfo:nil repeats:YES];
    });
}
@end
