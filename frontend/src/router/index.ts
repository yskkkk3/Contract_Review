import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/views/Layout.vue'),
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'contracts', name: 'contracts', component: () => import('@/views/ContractsView.vue') },
        { path: 'review', name: 'review', component: () => import('@/views/ReviewView.vue') },
        { path: 'compare', name: 'compare', component: () => import('@/views/CompareView.vue') },
        { path: 'chat', name: 'chat', component: () => import('@/views/ChatView.vue') },
        { path: 'admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('contract_review_token')
  if (!to.meta.public && !token) return { name: 'login' }
  if (to.name === 'login' && token) return { name: 'dashboard' }
  return true
})

export default router
