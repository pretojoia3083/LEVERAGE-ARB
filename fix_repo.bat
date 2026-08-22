@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
echo Limpando repo...
git rm --cached -f leverage_arb.db 2>nul
git rm --cached -f servidor.log 2>nul
git rm --cached -f deploy.bat 2>nul
git rm --cached -f deploy_nuvem.bat 2>nul
git rm --cached -f deploy_nuvem.py 2>nul
git rm --cached -f fix_repo.py 2>nul
git add .
git commit -m "fix: remove db, log and scripts"
git push origin master:main --force
echo.
echo PRONTO! Repo limpo e enviado.
pause