@echo off
chcp 65001 > nul
REM ============================================================
REM  四级英语 · 每日自动生成 + 推送
REM
REM  逻辑：算出「今天该是第几天」（从 progress.json 的 start_date 起算），
REM        生成当天内容并推送。如果电脑没开、错过了某天，
REM        下次开机时会把欠的一次性补上（一次跑多天）。
REM
REM  注册到计划任务（管理员 PowerShell 执行一次）：
REM    schtasks /create /tn "CET4-Daily" /tr "E:\english\cet4\每日推送.bat" /sc daily /st 07:00
REM ============================================================

cd /d "E:\english\cet4"

echo [%date% %time%] 开始 >> logs\daily.log

python build\daily.py >> logs\daily.log 2>&1

echo [%date% %time%] 结束 >> logs\daily.log
