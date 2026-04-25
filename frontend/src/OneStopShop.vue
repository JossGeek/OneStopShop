<script setup>
import { ref, onMounted } from 'vue'
import AppHeader from './components/layout/AppHeader.vue'
import Footer from './components/layout/AppFooter.vue'
import HeroSec from './components/sections/HeroSection.vue'
import UniBar from './components/sections/UniBar.vue'
import Stats from './components/sections/Stats.vue'
import Opportunities from './components/sections/Opportunities.vue'
import AboutSec from './components/sections/About.vue'
import HowItWorks from './components/sections/HowWorks.vue'
import Contacs from './components/sections/Contact.vue'
import ProfileSelection from './components/sections/ProfileSelection.vue'
import UserProfile from './components/sections/UserProfile.vue'

// 1. Состояние выбора роли (Задача: Dev root page)
const selectedRole = ref(null)

// 2. Состояние отображения профиля (Задача: User account center)
const showProfile = ref(false)

// Проверяем сохраненную роль при загрузке
onMounted(() => {
  const savedRole = localStorage.getItem('userRole')
  if (savedRole) {
    selectedRole.value = savedRole
  }
})

const handleRoleSelection = (role) => {
  selectedRole.value = role
  localStorage.setItem('userRole', role)
}

// Функция переключения вида (Лендинг <-> Профиль)
const toggleProfile = () => {
  showProfile.value = !showProfile.value
}

// Функция для выхода (сброс роли)
const logout = () => {
  localStorage.removeItem('userRole')
  selectedRole.value = null
  showProfile.value = false
}
</script>

<template>
  <ProfileSelection v-if="!selectedRole" @select-role="handleRoleSelection" />

  <div v-else class="app-container">
    <AppHeader @toggle-profile="showProfile = !showProfile" @logout="logout" :role="selectedRole" @go-home="showProfile = false" />

    <main class="content">
      <div v-if="showProfile">
        <UserProfile />
        <div class="text-center">
          <button @click="showProfile = false" class="back-btn">Back to Home</button>
        </div>
      </div>

      <div v-else>
        <div v-if="selectedRole === 'staff'" class="staff-welcome">
          <h2>Welcome, Colleague!</h2>
        </div>

        <HeroSec />
        <UniBar />
        <Stats />
        <Opportunities />
        <AboutSec />
        <HowItWorks />
        <Contacs />
      </div>
    </main>

    <Footer />
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.content {
  flex: 1; /* Чтобы футер всегда был внизу */
}

.staff-welcome {
  background: #f0f7ff;
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #dbeafe;
}

.staff-welcome h2 {
  color: #1e40af;
  margin: 0;
  font-size: 1.5rem;
}

.text-center {
  text-align: center;
  padding: 20px;
}

.back-btn {
  padding: 10px 20px;
  background: #111;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

.back-btn:hover {
  opacity: 0.8;
}
</style>