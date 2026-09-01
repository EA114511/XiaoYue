# 小玥 AI 语音助手 — Android 移动端

> 独立的 Android App，与网页版完全分离，专为移动端优化的语音助手体验。

---

## 技术栈

- **Vue 3** - 前端框架
- **Capacitor** - 跨平台打包
- **Vant 4** - 移动端 UI 组件库
- **Pinia** - 状态管理
- **Vue Router** - 路由

---

## 目录结构

```
mobile/
├── android/                # Android 原生工程
├── assets/                 # App 图标和启动画面素材
├── src/
│   ├── api/               # API 封装
│   ├── components/        # 组件
│   │   ├── VoiceOrb.vue   # 玥珠光球
│   │   ├── VoiceButton.vue # 录音按钮
│   │   └── MessageCard.vue # 消息卡片
│   ├── composables/       # 组合式函数
│   │   ├── useVoiceChat.js # 语音对话核心
│   │   └── useVAD.js      # VAD 检测
│   ├── router/            # 路由
│   ├── stores/            # Pinia 状态
│   ├── styles/            # 样式
│   │   └── main.css       # 「月夜·明珠」主题
│   ├── utils/             # 工具
│   │   └── constants.js   # 常量
│   ├── views/             # 页面
│   │   ├── HomeView.vue   # 主页
│   │   └── SettingsView.vue # 设置页
│   ├── App.vue            # 根组件
│   └── main.js            # 入口
├── capacitor.config.json  # Capacitor 配置
├── vite.config.js         # Vite 配置
└── package.json
```

---

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

---

## 打包 APK

### 前置要求

- JDK 17+
- Android Studio
- Android SDK

### 构建步骤

```bash
# 1. 构建前端
npm run build

# 2. 同步到 Android 工程
npx cap sync

# 3. 打开 Android Studio
npx cap open android
```

在 Android Studio 中：
1. **Build → Generate Signed Bundle / APK**
2. 选择或创建 keystore
3. 选择 **release** 构建
4. 输出 APK

详细步骤参见 `../docs/android-deployment.md`

---

## 与网页版的差异

| 维度 | 网页版 | 移动端 |
|------|--------|--------|
| 布局 | 双栏 | 单栏（上下） |
| 光球 | 420px | 160px |
| 组件库 | 自定义 | Vant 4 |
| 状态管理 | Composable | Pinia |
| 输入方式 | 输入坞 | 大按钮（底部固定） |
| 对话展示 | 完整列表 | 最近 3 条 |

---

## 配置 NAS 地址

首次启动 App 时，在设置页配置 NAS 地址：

1. 点击右上角设置图标
2. 输入 NAS 地址（如 `http://192.168.5.5:8000`）
3. 保存后自动连接

---

> 后端部署参见 `../docs/nas-deployment.md`
