#!/bin/zsh
# hossy から `open -a Terminal` で開かれる。R4 のコマンド(/tmp/hossy_r4_job.json)を動かし、終わったらこのウィンドウを閉じる
cd "${0:A:h}" || exit 1
/usr/bin/python3 -u runner.py

my_tty=$(tty)
( sleep 1; osascript -e "tell application \"Terminal\"
	repeat with w in windows
		if tty of tab 1 of w is \"$my_tty\" then close w
	end repeat
end tell" ) >/dev/null 2>&1 &!
exit 0
