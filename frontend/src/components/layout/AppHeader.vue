
<template>
    <nav :style="cssVars">
        <a class="nav-logo" href="#" @click.prevent="$emit('go-home')">Uni<span>Portal</span></a>
        
        <ul class="nav-links">
            <li><a href="#Opportunities">Opportunities</a></li>
            <li><a href="#about">About</a></li>
            <li><a href="#how">How it works</a></li>
            <li><a href="#contact">Contact</a></li>
        </ul>

        <div class="nav-right">
            <button class="profile-trigger" @click="$emit('toggle-profile')">
                <span class="avatar-mini">👤</span>
                My Profile
            </button>

            <a class="btn-nav" href="#opportunities">Browse opportunities</a>
            
            <button class="btn-logout" @click="$emit('logout')" title="Log out">
                🚪
            </button>
        </div>
    </nav>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// Объявляем события для связи с OneStopShop.vue
defineEmits(['toggle-profile', 'logout', 'go-home'])

const isScrolled = ref(false)

const onScroll = () => {
    isScrolled.value = window.scrollY > 80
}

onMounted(() => window.addEventListener('scroll', onScroll))
onUnmounted(() => window.removeEventListener('scroll', onScroll))

const cssVars = computed(() => ({
    '--ink': isScrolled.value ? '#ffffff' : '#111110',
    '--ink-soft': isScrolled.value ? '#ffffff' : '#111110',
    '--surface': isScrolled.value ? '#111110' : '#ffffff',
    '--border': isScrolled.value ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'
}))
</script>

<!-- <style scoped>
nav {
    position: fixed;
    top: 0; left: 0; right: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 40px;
    background-color: var(--surface);
    color: var(--ink);
    transition: all 0.3s ease;
    z-index: 1000;
    border-bottom: 1px solid var(--border);
}

.nav-logo {
    font-size: 24px;
    font-weight: 800;
    text-decoration: none;
    color: var(--ink);
}

.nav-logo span { color: #3b82f6; }

.nav-links {
    display: flex;
    list-style: none;
    gap: 30px;
    margin: 0;
}

.nav-links a {
    text-decoration: none;
    color: var(--ink-soft);
    font-weight: 500;
    font-size: 15px;
}

.nav-right {
    display: flex;
    align-items: center;
    gap: 20px;
}




</style> -->