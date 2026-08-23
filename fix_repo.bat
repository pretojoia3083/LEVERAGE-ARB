@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: usar fetch_ticker individual por exchange em vez de fetch_tickers"
git push origin master:main --force
echo DONE
pause