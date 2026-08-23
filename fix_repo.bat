@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: buscar ticker de todas exchanges sem filtro de markets"
git push origin master:main --force
echo DONE
pause