<template>
  <section class="selection-screen">
    <div class="container">
      <div class="text-center">
        <h1 class="title">Welcome to <span>UniPortal</span></h1>
        <p class="subtitle">Select your profile to view tailored content</p>
      </div>

      <div class="grid-profiles">
        <div class="profile-card" @click="navigateTo('student')">
          <div class="icon">🎓</div>
          <h3>Student</h3>
          <p>Access courses, grades, and campus services effortlessly.</p>
          <button class="select-btn">Continue as Student</button>
        </div>

        <div class="profile-card" @click="navigateTo('staff')">
          <div class="icon">💼</div>
          <h3>Academic Staff</h3>
          <p>Manage teaching materials, research, and administrative tasks.</p>
          <button class="select-btn">Continue as Staff</button>
        </div>

        <div class="profile-card" @click="navigateTo('external')">
          <div class="icon">🌐</div>
          <h3>External User</h3>
          <p>Discover public events, partnerships, and general information.</p>
          <button class="select-btn">Explore Portal</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
const emit = defineEmits(['select-role']);

const navigateTo = (role) => {
  console.log('Selected role:', role);
  // Здесь мы отправляем событие родителю, что роль выбрана
  emit('select-role', role);
};
</script>

