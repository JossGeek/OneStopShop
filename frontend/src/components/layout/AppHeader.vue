<template>
    <nav :style="cssVars">
        <a class="nav-logo" href="#">Uni<span>Portal</span></a>
        <ul class="nav-links">
            <li><a href="#Opportunities">Opportunities</a></li>
            <li><a href="#about">About</a></li>
            <li><a href="#how">How it works</a></li>
            <li><a href="#contact">Contact</a></li>
        </ul>
        <div class="nav-right">
            <a class="btn-nav" href="#opportunities">Browse opportunities</a>
        </div>
    </nav>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const isScrolled = ref(false)

const onScroll = () => {
  isScrolled.value = window.scrollY > 80
}

onMounted(() => window.addEventListener('scroll', onScroll))
onUnmounted(() => window.removeEventListener('scroll', onScroll))

const cssVars = computed(() => ({
  '--ink': isScrolled.value ? '#ffffff' : '#111110',
  '--ink-soft': isScrolled.value ? '#ffffff' : '#111110',
  '--surface': isScrolled.value ? '#111110' : '#ffffff'
}))
</script>