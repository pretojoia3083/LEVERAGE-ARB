@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: saldos + toggle auto/manual + API keys config"
git push origin master:main --force
echo DONE
pause