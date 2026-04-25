<template>
  <div class="profile-container">
    <div class="profile-card">
      <div class="profile-header">
        <div class="avatar-circle">
          {{ user.name.charAt(0) }}
        </div>
        <div class="header-info">
          <h2>{{ user.name }}</h2>
          <span class="role-badge">{{ user.role }}</span>
        </div>
      </div>

      <div class="profile-details">
        <div class="detail-item">
          <label>Email Address</label>
          <p>{{ user.email }}</p>
        </div>
        
        <div class="detail-item">
          <label>Student ID / Staff Number</label>
          <p>{{ user.idNumber }}</p>
        </div>

        <div class="detail-item">
          <label>Department / Faculty</label>
          <p>{{ user.department }}</p>
        </div>
      </div>

      <div class="user-sections">
  <div class="section-box">
    <h3>My Needs & Offers</h3>
    <div class="placeholder-info">You haven't posted any offers yet.</div>
  </div>

  <div class="section-box">
    <h3>Saved Favorites</h3>
    <ul class="favorites-list">
      <li>⭐ International Exchange Program</li>
      <li>⭐ Library Digital Access</li>
    </ul>
  </div>
</div>

      <div class="profile-actions">
        <button class="edit-btn">Edit Profile</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// Пока бэкенд в процессе (WIP), используем заглушку (mock data)
const user = ref({
  name: 'Uladzislau Zhukau',
  role: 'Student',
  email: 'u.zhukau@university.edu',
  idNumber: 'ST-123456',
  department: 'Faculty of Computer Science'
})
</script>

