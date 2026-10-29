@echo off
title Generador de imagenes de producto
echo Iniciando software...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar el programa.
    pause
)
