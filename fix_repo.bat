@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: skip load_markets for binance on cloud, retry with 60s timeout"
git push origin master:main --force
echo DONE
pause