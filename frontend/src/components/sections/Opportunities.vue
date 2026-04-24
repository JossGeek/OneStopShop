<template>
  <section id="Opportunities">
    <div class="section-header">
      <div>
        <p class="section-eyebrow">Latest listings</p>
        <h2 class="section-title">Browse opportunities</h2>
      </div>
      <a class="section-link" href="#" @click.prevent="resetFilters">Reset filters</a>
    </div>

    <div class="filter-bar">
      <input 
        v-model="searchQuery" 
        class="search-input" 
        type="text" 
        placeholder="Search by keyword, topic, department..."
      />
      
      <select v-model="selectedUni" class="filter-select">
        <option>All universities</option>
        <option v-for="u in uniOptions" :key="u">{{ u }}</option>
      </select>

      <button 
        v-for="cat in categories" 
        :key="cat"
        @click="activeCat = cat"
        :class="['filter-chip', { active: activeCat === cat }]"
      >
        {{ cat }}
      </button>
    </div>

    <div class="cards-grid">
      <div v-for="opp in filteredList" :key="opp.id" class="opp-card">
        <div class="card-top">
          <span :class="['type-tag', opp.tagClass]">{{ opp.typeLabel }}</span>
          <div class="uni-logo-sm">{{ opp.uniShort }}</div>
        </div>
        
        <div class="card-title">{{ opp.title }}</div>
        
        <div class="card-meta">
          <div class="card-meta-row">
            <svg viewBox="0 0 24 24"><path d="M20 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 3v4M8 3v4"/></svg>
            {{ opp.university }}
          </div>
          <div class="card-meta-row">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            {{ opp.duration }}
          </div>
          <div class="card-meta-row">
            <svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>
            {{ opp.location }}
          </div>
        </div>

        <div class="card-footer">
          <span class="deadline">Deadline: {{ opp.deadline }}</span>
          <a class="btn-view" :href="opp.link">View at {{ opp.uniShort }}</a>
        </div>
      </div>
    </div>

    <div v-if="filteredList.length === 0" style="text-align: center; padding: 40px; color: #888;">
      No opportunities found matching your criteria.
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue';
import { rawOpportunities, applyFilters } from './opportunities.js';

// Состояние
const searchQuery = ref('');
const selectedUni = ref('All universities');
const activeCat = ref('All');

const categories = ['All', 'Thesis', 'Internship', 'Jobs', 'Courses'];
const uniOptions = [
  'KTH Royal Institute', 
  'Uppsala University', 
  'Lund University', 
  'Chalmers', 
  'Linköping University'
];

const filteredList = computed(() => {
  return applyFilters(rawOpportunities, {
    query: searchQuery.value,
    uni: selectedUni.value,
    cat: activeCat.value
  });
});

const resetFilters = () => {
  searchQuery.value = '';
  selectedUni.value = 'All universities';
  activeCat.value = 'All';
};
</script>

<style scoped>
.filter-chip { cursor: pointer; transition: 0.2s; }
.filter-chip.active { background: #000; color: #fff; border-color: #000; }
.btn-view { text-decoration: none; }
</style>