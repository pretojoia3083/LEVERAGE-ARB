@echo off
cd /d "C:\Users\Renato\Desktop\projetos code ia\LEVERAGE ARB"
git add .
git commit -m "fix: MEXC via requests direto com BRLUSDT invertido"
git push origin master:main --force
echo DONE
pause