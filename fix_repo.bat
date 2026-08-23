@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: add Binance API key support"
git push origin master:main --force
echo DONE
pause