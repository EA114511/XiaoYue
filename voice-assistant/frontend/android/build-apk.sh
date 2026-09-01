#!/bin/bash
# ============================================
# 小玥 AI 语音助手 - APK 构建脚本 (Linux/Mac)
# ============================================

echo ""
echo "========================================"
echo "  小玥 AI 语音助手 - APK 构建脚本"
echo "========================================"
echo ""

# 检查 Java 环境
if ! command -v java &> /dev/null; then
    echo "[错误] 未找到 Java，请先安装 JDK 17+"
    echo "下载地址: https://www.oracle.com/java/technologies/downloads/"
    exit 1
fi

echo "[√] Java 环境检查通过"
java -version

# 检查 Android SDK
if [ -z "$ANDROID_HOME" ]; then
    echo "[警告] ANDROID_HOME 环境变量未设置"
    echo "请确保已安装 Android Studio 并配置 SDK"
    echo ""
    read -p "是否继续？(y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        exit 1
    fi
else
    echo "[√] ANDROID_HOME: $ANDROID_HOME"
fi

# 进入 Android 目录
cd "$(dirname "$0")"

# 检查 keystore
if [ ! -f keystore.properties ]; then
    echo ""
    echo "[提示] 首次构建需要创建 keystore"
    echo ""

    read -p "是否创建新的 keystore？(y/n): " CREATE_KEYSTORE
    if [ "$CREATE_KEYSTORE" = "y" ] || [ "$CREATE_KEYSTORE" = "Y" ]; then
        ./create-keystore.sh
        if [ $? -ne 0 ]; then
            echo "[错误] keystore 创建失败"
            exit 1
        fi
    else
        echo "[跳过] keystore 创建"
        echo "请手动复制 keystore.properties.template 为 keystore.properties 并填入信息"
        exit 1
    fi
fi

# 构建 APK
echo ""
echo "[构建] 正在构建 Release APK..."
echo ""

./gradlew assembleRelease

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "  [成功] APK 构建完成！"
    echo "========================================"
    echo ""
    echo "输出路径:"
    echo "  $(pwd)/app/build/outputs/apk/release/app-release.apk"
    echo ""
    echo "文件大小:"
    ls -lh app/build/outputs/apk/release/app-release.apk
    echo ""
else
    echo ""
    echo "[错误] 构建失败，请检查上方错误信息"
    echo ""
fi
