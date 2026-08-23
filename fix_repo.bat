@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: incluir mercadobitcoin no snapshot de precos"
git push origin master:main --force
echo DONE
pause