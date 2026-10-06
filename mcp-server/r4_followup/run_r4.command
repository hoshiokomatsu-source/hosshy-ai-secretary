#!/bin/zsh
# hossy から `open -a Terminal` で開かれる。R4自動処理を走らせ、終わったらこのウィンドウを閉じる
cd "${0:A:h}" || exit 1
R4_DIR=$(/usr/bin/python3 -c 'import json; print(json.load(open("/tmp/hossy_r4_job.json"))["r4_dir"])')
echo "ホッシーくん: R4自動処理をしています。終わるまでマウスとキーボードに触らないでください。"
# caffeinate -d: 作業中に画面が消えないようにする
caffeinate -dimsu "$R4_DIR/venv/bin/python" -u runner.py

my_tty=$(tty)
( sleep 1; osascript -e "tell application \"Terminal\"
	repeat with w in windows
		if tty of tab 1 of w is \"$my_tty\" then close w
	end repeat
end tell" ) >/dev/null 2>&1 &!
exit 0
