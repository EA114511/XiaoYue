import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/main.css'

// Vant 组件按需引入
import {
  NavBar,
  Button,
  Icon,
  Cell,
  CellGroup,
  Field,
  Switch,
  Toast,
  Dialog,
  Loading
} from 'vant'

const app = createApp(App)
const pinia = createPinia()

// 注册 Vant 组件
const vantComponents = [
  NavBar, Button, Icon, Cell, CellGroup, Field, Switch, Toast, Dialog, Loading
]
vantComponents.forEach(component => {
  app.use(component)
})

app.use(pinia)
app.use(router)

app.mount('#app')
