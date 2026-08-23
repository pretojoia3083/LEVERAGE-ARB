@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
echo. >> .gitignore
git add .
git commit -m "chore: force redeploy"
git push origin master:main --force
echo DONE
pause