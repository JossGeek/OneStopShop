<script setup>
import { ref } from 'vue'
import Header from './components/layout/AppHeader.vue'
import Footer from './components/layout/AppFooter.vue'
import HeroSec from './components/sections/HeroSection.vue'
import UniBar from './components/sections/UniBar.vue'
import Stats from './components/sections/Stats.vue'
import Opportunietes from './components/sections/Opportunities.vue'
import AboutSec from './components/sections/About.vue'
import HowItWorks from './components/sections/HowWorks.vue'
import Contacs from './components/sections/Contact.vue'


</script>

<template>

  <Header />

  <main>
    <HeroSec />
    <UniBar />
    <Stats />
    <Opportunietes />
    <AboutSec />
    <HowItWorks />
    <Contacs />
  </main>

  <Footer />

</template>