#!/bin/bash
# ============================================
# 创建 Release Keystore (Linux/Mac)
# ============================================

echo ""
echo "========================================"
echo "  创建 Keystore 签名证书"
echo "========================================"
echo ""

# 设置默认路径
KEYSTORE_DIR="$(dirname "$0")/keystore"
KEYSTORE_FILE="$KEYSTORE_DIR/xiaoyue-release.jks"

# 创建目录
mkdir -p "$KEYSTORE_DIR"

# 获取用户输入
read -s -p "请输入 Keystore 密码（至少6位）: " STORE_PASSWORD
echo ""
read -s -p "请输入 Key 密码（可与上面相同）: " KEY_PASSWORD
echo ""
read -p "请输入 Key 别名 [默认: xiaoyue]: " KEY_ALIAS
KEY_ALIAS=${KEY_ALIAS:-xiaoyue}

echo ""
echo "请填写证书信息（可直接回车使用默认值）:"
read -p "您的名字或组织 [默认: 小玥]: " CN
CN=${CN:-小玥}

read -p "组织单位 [默认: Voice Assistant]: " OU
OU=${OU:-Voice Assistant}

read -p "组织名称 [默认: XiaoYue]: " O
O=${O:-XiaoYue}

read -p "城市 [默认: Beijing]: " L
L=${L:-Beijing}

read -p "省份 [默认: Beijing]: " ST
ST=${ST:-Beijing}

read -p "国家代码 [默认: CN]: " C
C=${C:-CN}

echo ""
echo "[生成] 正在创建 keystore..."
echo "文件: $KEYSTORE_FILE"
echo ""

keytool -genkey -v \
    -keystore "$KEYSTORE_FILE" \
    -alias "$KEY_ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$STORE_PASSWORD" \
    -keypass "$KEY_PASSWORD" \
    -dname "CN=$CN, OU=$OU, O=$O, L=$L, ST=$ST, C=$C"

if [ $? -ne 0 ]; then
    echo "[错误] keystore 创建失败"
    exit 1
fi

echo "[√] keystore 创建成功"

# 创建 keystore.properties
echo ""
echo "[配置] 正在创建 keystore.properties..."

cat > keystore.properties << EOF
storeFile=keystore/xiaoyue-release.jks
storePassword=$STORE_PASSWORD
keyAlias=$KEY_ALIAS
keyPassword=$KEY_PASSWORD
EOF

echo "[√] keystore.properties 已创建"

echo ""
echo "========================================"
echo "  完成！"
echo "========================================"
echo ""
echo "文件位置:"
echo "  Keystore: $KEYSTORE_FILE"
echo "  配置: $(dirname "$0")/keystore.properties"
echo ""
echo "重要提示:"
echo "  1. 请妥善保管 keystore 文件和密码"
echo "  2. 丢失 keystore 将无法更新已发布的 App"
echo "  3. 建议将 keystore 备份到安全位置"
echo ""
