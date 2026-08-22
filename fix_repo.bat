@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git rm --cached -f fix_repo.py 2>nul
git add .
git commit -m "fix: pin Python 3.12 for Render"
git push origin master:main --force
echo DONE
pause