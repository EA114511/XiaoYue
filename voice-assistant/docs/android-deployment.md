# 小玥 AI 语音助手 — Android App 打包指南

> 将 Vue 3 前端打包为独立 Android APK，可安装到手机使用。

---

## 前提条件

| 工具 | 版本 | 用途 |
|------|------|------|
| Node.js | 18+ | 前端构建 |
| Android Studio | 最新版 | APK 打包、签名 |
| Android SDK | API 33+ | 编译 Android 应用 |
| JDK | 17+ | Gradle 构建 |

---

## 快速开始

### 1. 安装依赖

```bash
cd voice-assistant/frontend
npm install
npm install @capacitor/core @capacitor/cli @capacitor/android
```

### 2. 构建前端

```bash
npm run build
```

构建产物输出到 `dist/` 目录。

### 3. 同步到 Android 工程

```bash
npx cap sync
```

### 4. 打开 Android Studio

```bash
npx cap open android
```

或手动用 Android Studio 打开 `frontend/android/` 目录。

---

## 配置说明

### capacitor.config.json

```json
{
  "appId": "com.xiaoyue.voice",
  "appName": "小玥",
  "webDir": "dist",
  "server": {
    "url": "http://192.168.5.5:8000",
    "cleartext": true
  },
  "android": {
    "allowMixedContent": true,
    "captureInput": true
  }
}
```

| 配置项 | 说明 |
|--------|------|
| `server.url` | NAS 后端地址，打包前改为实际 NAS IP |
| `cleartext` | 允许 HTTP（局域网 NAS 通常无 HTTPS） |
| `allowMixedContent` | 允许 HTTP 资源加载 |

---

## 配置签名（Keystore）

### 首次构建：创建 Keystore

**方式一：使用脚本自动创建（推荐）**

**Windows**：
```cmd
cd voice-assistant\frontend\android
create-keystore.bat
```

**Linux / Mac**：
```bash
cd voice-assistant/frontend/android
./create-keystore.sh
```

按提示输入：
- Keystore 密码（至少 6 位）
- Key 密码（可与上面相同）
- Key 别名（默认：xiaoyue）
- 证书信息（可直接回车使用默认值）

**方式二：手动创建**

```bash
cd voice-assistant/frontend/android

# 创建 keystore
keytool -genkey -v \
    -keystore keystore/xiaoyue-release.jks \
    -alias xiaoyue \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000

# 复制配置模板
cp keystore.properties.template keystore.properties

# 编辑 keystore.properties，填入实际密码
```

**方式三：Android Studio 创建**

1. **Build → Generate Signed Bundle / APK**
2. 点击 **Create new...**
3. 填写信息并保存

### 已有 Keystore：配置密码

编辑 `frontend/android/keystore.properties`：

```properties
storeFile=keystore/xiaoyue-release.jks
storePassword=你的keystore密码
keyAlias=xiaoyue
keyPassword=你的key密码
```

> ⚠️ **重要**：`keystore.properties` 包含敏感信息，已添加到 `.gitignore`，不会提交到 Git。

---

## 生成签名 APK

### 方式一：一键构建脚本（推荐）

**Windows**：
```cmd
cd voice-assistant\frontend\android
build-apk.bat
```

**Linux / Mac**：
```bash
cd voice-assistant/frontend/android
./build-apk.sh
```

脚本会自动：
1. 检查 Java 和 Android SDK 环境
2. 首次运行时引导创建 keystore
3. 构建 Release APK

### 方式二：Android Studio 图形界面

1. 在 Android Studio 中打开 `frontend/android/`
2. 等待 Gradle 同步完成
3. 点击 **Build → Generate Signed Bundle / APK**
4. 选择 **APK**，点击 Next
5. 选择已创建的 keystore（或点击 **Create new...** 创建）
6. 输入 keystore 密码和 key 密码
7. 选择 **release** 构建类型
8. 点击 **Finish**

APK 输出位置：
```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

### 方式三：命令行构建

```bash
cd frontend/android

# Windows
gradlew.bat assembleRelease

# Linux / Mac
./gradlew assembleRelease
```

APK 输出位置：
```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

---

## 安装到手机

### 方式一：USB 安装（调试）

1. 手机开启「开发者模式」和「USB 调试」
2. 连接电脑
3. 在 Android Studio 中点击 **Run 'app'**

### 方式二：APK 文件安装

1. 将 `app-release.apk` 发送到手机（微信 / QQ / 邮件 / USB）
2. 手机点击 APK 文件
3. 允许「安装未知来源应用」
4. 安装完成后打开

---

## 常见问题

### Q1: 打包后无法连接 NAS？

**检查项**：
1. `capacitor.config.json` 中的 `server.url` 是否正确指向 NAS IP
2. 手机与 NAS 是否在同一局域网
3. NAS 防火墙是否允许 8000 端口
4. 后端是否正常运行：`curl http://nas-ip:8000/api/v1/health/status`

### Q2: 麦克风权限被拒绝？

AndroidManifest.xml 中需包含：

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
```

首次启动时 App 会请求权限，请在系统弹窗中允许。

### Q3: 唤醒词功能不可用？

Android WebView 中 `SpeechRecognition` API 通常不可用，这是正常限制。

**降级方案**：
- App 会自动检测并提示
- 用户仍可通过「按住说话」按钮进行语音输入

### Q4: 如何更新 App？

1. 修改代码后重新执行 `npm run build`
2. 执行 `npx cap sync`
3. 在 Android Studio 中重新生成签名 APK
4. 卸载旧版本或覆盖安装

---

## 进阶：自定义 App 图标和启动画面

### 准备素材

在 `frontend/assets/` 目录创建：

| 文件 | 尺寸 | 说明 |
|------|------|------|
| `icon-only.png` | 512x512 | App 图标 |
| `icon-foreground.png` | 512x512 | 前景图标（透明背景） |
| `icon-background.png` | 512x512 | 背景色 `#090C14` |
| `splash.png` | 2732x2732 | 启动画面 |
| `splash-dark.png` | 2732x2732 | 暗色启动画面 |

### 自动生成

```bash
npm install -g @capacitor/assets
npx capacitor-assets generate --android
```

生成后会自动更新 `frontend/android/app/src/main/res/` 目录。

---

## 安全建议

1. **keystore 备份**：妥善保存 `xiaoyue.jks` 文件和密码，丢失后无法更新 App
2. **API Token**：生产环境务必设置强 `API_TOKEN`，防止未授权访问
3. **代码混淆**：如需发布，建议开启 ProGuard 混淆

---

> 详细配置参考：[Capacitor 官方文档](https://capacitorjs.com/docs)
