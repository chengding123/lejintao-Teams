@echo off
setlocal
for %%I in ("%~dp0..\..") do set "COURSE_ROOT=%%~fI"
docker.exe compose --project-directory "%COURSE_ROOT%" --env-file "%COURSE_ROOT%\deployment\offline\runtime.env" --file "%COURSE_ROOT%\compose.yaml" --file "%COURSE_ROOT%\deployment\experiment3.override.yaml" --project-name cinelab up -d --no-build --pull never --wait --wait-timeout 300 api web
if errorlevel 1 (
  echo Experiment 3 did not start. Check Docker Desktop and the local student images.
  exit /b 1
)
echo Experiment 3 is ready: http://127.0.0.1:8080/experiments?source=ml^&algorithm=als^&user=14
