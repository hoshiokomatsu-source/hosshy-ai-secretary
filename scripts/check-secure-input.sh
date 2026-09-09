#!/bin/bash
# Secure Input が loginwindow に捕まったまま残っていたら通知する

RESULT=$(ioreg -l -d 1 -w 0 | grep -o 'kCGSSessionSecureInputPID"=[0-9]*' | grep -o '[0-9]*$')

if [ -z "$RESULT" ]; then
  exit 0
fi

APP=$(ps -p "$RESULT" -o comm= 2>/dev/null)

# loginwindow が持ったままで、かつ lock screen が出ていない場合は stuck とみなす
# ロック中かどうかは screensaver プロセスで判定
SCREENSAVER=$(pgrep -x ScreenSaverEngine 2>/dev/null)

if [[ "$APP" == *"loginwindow"* ]] && [ -z "$SCREENSAVER" ]; then
  osascript -e 'display notification "画面ロック→解除すれば直ります" with title "⌨️ キーボードが効かなくなってます" sound name "Funk"'
fi
