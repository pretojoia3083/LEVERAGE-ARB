@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: binance load_markets with 60s timeout on cloud"
git push origin master:main --force
echo DONE
pause