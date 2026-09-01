@echo off
REM ============================================
REM 小玥 AI 语音助手 - APK 构建脚本 (Windows)
REM ============================================

echo.
echo ========================================
echo   小玥 AI 语音助手 - APK 构建脚本
echo ========================================
echo.

REM 检查 Java 环境
where java >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Java，请先安装 JDK 17+
    echo 下载地址: https://www.oracle.com/java/technologies/downloads/
    pause
    exit /b 1
)

echo [√] Java 环境检查通过
java -version

REM 检查 Android SDK
if not defined ANDROID_HOME (
    echo [警告] ANDROID_HOME 环境变量未设置
    echo 请确保已安装 Android Studio 并配置 SDK
    echo.
    set /p CONTINUE="是否继续？(y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
) else (
    echo [√] ANDROID_HOME: %ANDROID_HOME%
)

REM 进入 Android 目录
cd /d "%~dp0"

REM 检查 keystore
if not exist keystore.properties (
    echo.
    echo [提示] 首次构建需要创建 keystore
    echo.

    set /p CREATE_KEYSTORE="是否创建新的 keystore？(y/n): "
    if /i "%CREATE_KEYSTORE%"=="y" (
        call create-keystore.bat
        if %errorlevel% neq 0 (
            echo [错误] keystore 创建失败
            pause
            exit /b 1
        )
    ) else (
        echo [跳过] keystore 创建
        echo 请手动复制 keystore.properties.template 为 keystore.properties 并填入信息
        pause
        exit /b 1
    )
)

REM 构建 APK
echo.
echo [构建] 正在构建 Release APK...
echo.

call gradlew.bat assembleRelease

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   [成功] APK 构建完成！
    echo ========================================
    echo.
    echo 输出路径:
    echo   %CD%\app\build\outputs\apk\release\app-release.apk
    echo.
    echo 文件大小:
    dir app\build\outputs\apk\release\app-release.apk | find "app-release.apk"
    echo.
) else (
    echo.
    echo [错误] 构建失败，请检查上方错误信息
    echo.
)

pause
