@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: preservar erros do _fetch_direct"
git push origin master:main --force
echo DONE
pause