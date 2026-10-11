<template>
  <div class="login-page">
    <div class="login-shell">
      <div class="brand-panel">
        <div class="brand-head">
          <svg class="brand-logo" viewBox="0 0 48 48" width="44" height="44" aria-hidden="true">
            <defs>
              <linearGradient id="lg2" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#60a5fa" />
                <stop offset="1" stop-color="#2563eb" />
              </linearGradient>
            </defs>
            <path d="M24 4l14 5.2v11.6c0 9.1-5.9 16.6-14 20.2-8.1-3.6-14-11.1-14-20.2V9.2L24 4z" fill="url(#lg2)" />
            <path d="M16 24.5l5.5 5.5L32.5 18.5" stroke="#fff" stroke-width="3.4" fill="none" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <div>
            <div class="brand-title">高校合同智能审阅系统</div>
            <div class="brand-sub">Contract Review Agent</div>
          </div>
        </div>
        <ul class="feature-list">
          <li><span class="dot" />多智能体编排 · LangGraph 意图识别 / 专家并行 / 仲裁</li>
          <li><span class="dot" />混合检索 RAG · 法规 / 校内制度 / 合同模板三层知识库</li>
          <li><span class="dot" />流式审阅 · SSE 实时输出风险点与修改建议</li>
        </ul>
        <div class="brand-footer">深圳大学 · 采购合同管理场景</div>
      </div>
      <el-card class="login-card" shadow="never">
        <h2>欢迎回来</h2>
        <p class="login-tip">登录以使用合同智能审阅能力</p>
        <el-tabs v-model="tab">
          <el-tab-pane label="登录" name="login">
            <el-form @keyup.enter="onLogin">
              <el-form-item>
                <el-input v-model="identifier" placeholder="用户名 / 邮箱" size="large" clearable />
              </el-form-item>
              <el-form-item>
                <el-input v-model="password" type="password" placeholder="密码" size="large" show-password />
              </el-form-item>
              <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="onLogin">登 录</el-button>
            </el-form>
          </el-tab-pane>
          <el-tab-pane label="注册" name="register">
            <el-form @keyup.enter="onRegister">
              <el-form-item>
                <el-input v-model="reg.username" placeholder="用户名" size="large" clearable />
              </el-form-item>
              <el-form-item>
                <el-input v-model="reg.password" type="password" placeholder="密码" size="large" show-password />
              </el-form-item>
              <el-form-item>
                <el-input v-model="reg.displayName" placeholder="姓名（可选）" size="large" clearable />
              </el-form-item>
              <el-form-item>
                <el-input v-model="reg.department" placeholder="部门（可选）" size="large" clearable />
              </el-form-item>
              <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="onRegister">注 册</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const tab = ref('login')
const identifier = ref('')
const password = ref('')
const reg = reactive({ username: '', password: '', displayName: '', department: '' })
const loading = ref(false)

async function onLogin() {
  loading.value = true
  try {
    await auth.login(identifier.value, password.value)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  loading.value = true
  try {
    await auth.register(reg.username, reg.password, reg.displayName, reg.department)
    ElMessage.success('注册成功，请登录')
    tab.value = 'login'
    identifier.value = reg.username
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(1200px 600px at 15% 10%, rgba(37, 99, 235, 0.18), transparent 60%),
    radial-gradient(1000px 500px at 85% 90%, rgba(124, 58, 237, 0.14), transparent 55%),
    linear-gradient(135deg, #0f172a, #1e3a8a);
  padding: 24px;
}

.login-shell {
  display: flex;
  width: 880px;
  max-width: 100%;
  min-height: 520px;
  border-radius: 16px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 24px 60px rgba(2, 6, 23, 0.35);
}

.brand-panel {
  flex: 1.1;
  padding: 44px 40px;
  color: #fff;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(160deg, rgba(37, 99, 235, 0.35), rgba(15, 23, 42, 0.15)),
    #1e3a8a;
}

.brand-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.brand-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  margin-top: 2px;
  letter-spacing: 1px;
}

.feature-list {
  list-style: none;
  margin: 40px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.88);
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  line-height: 1.5;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.2);
  flex-shrink: 0;
}

.brand-footer {
  margin-top: auto;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

.login-card {
  flex: 1;
  border: none;
  box-shadow: none;
  padding: 40px 8px 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.login-card :deep(.el-card__body) {
  width: 100%;
}

h2 {
  margin: 0;
  color: #0f172a;
  font-size: 22px;
}

.login-tip {
  margin: 8px 0 22px;
  color: #94a3b8;
  font-size: 13px;
}

.login-card :deep(.el-tabs__item) {
  font-size: 15px;
}
</style>
