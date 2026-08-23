@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "feat: load exchanges sequentially on cloud for memory"
git push origin master:main --force
echo DONE
pause