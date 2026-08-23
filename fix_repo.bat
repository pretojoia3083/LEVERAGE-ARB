@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: fallback to minimal market for binance/bybit on cloud"
git push origin master:main --force
echo DONE
pause