@echo off
REM ============================================
REM 创建 Release Keystore
REM ============================================

echo.
echo ========================================
echo   创建 Keystore 签名证书
echo ========================================
echo.

REM 设置默认路径
set KEYSTORE_DIR=%~dp0keystore
set KEYSTORE_FILE=%KEYSTORE_DIR%\xiaoyue-release.jks

REM 创建目录
if not exist %KEYSTORE_DIR% mkdir %KEYSTORE_DIR%

REM 获取用户输入
set /p STORE_PASSWORD="请输入 Keystore 密码（至少6位）: "
set /p KEY_PASSWORD="请输入 Key 密码（可与上面相同）: "
set /p KEY_ALIAS="请输入 Key 别名 [默认: xiaoyue]: "
if "%KEY_ALIAS%"=="" set KEY_ALIAS=xiaoyue

echo.
echo 请填写证书信息（可直接回车使用默认值）:
set /p CN="您的名字或组织 [默认: 小玥]: "
if "%CN%"=="" set CN=小玥

set /p OU="组织单位 [默认: Voice Assistant]: "
if "%OU%"=="" set OU=Voice Assistant

set /p O="组织名称 [默认: XiaoYue]: "
if "%O%"=="" set O=XiaoYue

set /p L="城市 [默认: Beijing]: "
if "%L%"=="" set L=Beijing

set /p ST="省份 [默认: Beijing]: "
if "%ST%"=="" set ST=Beijing

set /p C="国家代码 [默认: CN]: "
if "%C%"=="" set C=CN

echo.
echo [生成] 正在创建 keystore...
echo 文件: %KEYSTORE_FILE%
echo.

keytool -genkey -v ^
    -keystore "%KEYSTORE_FILE%" ^
    -alias %KEY_ALIAS% ^
    -keyalg RSA ^
    -keysize 2048 ^
    -validity 10000 ^
    -storepass %STORE_PASSWORD% ^
    -keypass %KEY_PASSWORD% ^
    -dname "CN=%CN%, OU=%OU%, O=%O%, L=%L%, ST=%ST%, C=%C%"

if %errorlevel% neq 0 (
    echo [错误] keystore 创建失败
    pause
    exit /b 1
)

echo [√] keystore 创建成功

REM 创建 keystore.properties
echo.
echo [配置] 正在创建 keystore.properties...

(
echo storeFile=keystore/xiaoyue-release.jks
echo storePassword=%STORE_PASSWORD%
echo keyAlias=%KEY_ALIAS%
echo keyPassword=%KEY_PASSWORD%
) > keystore.properties

echo [√] keystore.properties 已创建

echo.
echo ========================================
echo   完成！
echo ========================================
echo.
echo 文件位置:
echo   Keystore: %KEYSTORE_FILE%
echo   配置: %~dp0keystore.properties
echo.
echo 重要提示:
echo   1. 请妥善保管 keystore 文件和密码
echo   2. 丢失 keystore 将无法更新已发布的 App
echo   3. 建议将 keystore 备份到安全位置
echo.

pause
