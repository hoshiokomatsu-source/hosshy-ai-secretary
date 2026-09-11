#!/bin/bash
# Secure Input がスタックしていたら displaysleepnow で自動解除する

RESULT=$(ioreg -l -d 1 -w 0 | grep -o 'kCGSSessionSecureInputPID"=[0-9]*' | grep -o '[0-9]*$')

if [ -z "$RESULT" ]; then
  exit 0
fi

APP=$(ps -p "$RESULT" -o comm= 2>/dev/null)

# ロック画面が出ていないのに Secure Input が残っている = stuck
SCREENSAVER=$(pgrep -x ScreenSaverEngine 2>/dev/null)
LOCKSCREEN=$(pgrep -x loginwindow 2>/dev/null)

if [ -z "$SCREENSAVER" ]; then
  # プロセスが死んでいる or loginwindow がロック中でない場合
  if [ -z "$APP" ] || [[ "$APP" == *"loginwindow"* ]]; then
    echo "$(date): Secure Input stuck (PID=$RESULT, APP=$APP) → displaysleepnow で自動解除"
    # ディスプレイをスリープさせてロック画面を出す（ユーザーが解除することで SecureInput がリセットされる）
    pmset displaysleepnow
    # 通知も出す
    osascript -e 'display notification "画面ロック→Touch IDで解除してください（自動検知）" with title "⌨️ キーボードが効かなくなってました" sound name "Funk"'
  fi
fi
