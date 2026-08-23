@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: add Bitget API key support via .env"
git push origin master:main --force
echo DONE
pause