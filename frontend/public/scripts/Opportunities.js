export const rawOpportunities = [
  {
    id: 1,
    category: 'Thesis',
    typeLabel: 'Master thesis',
    tagClass: 'tag-thesis',
    uniShort: 'KTH',
    university: 'KTH Royal Institute of Technology',
    title: 'AI-driven energy optimisation in smart grid systems',
    duration: 'Full-time · 6 months',
    location: 'Stockholm, Sweden',
    deadline: '15 May 2026',
    link: '#'
  },
  {
    id: 2,
    category: 'Internship',
    typeLabel: 'Internship',
    tagClass: 'tag-intern',
    uniShort: 'LU',
    university: 'Lund University',
    title: 'Sustainability research intern — Materials Science Lab',
    duration: 'Part-time · 3 months',
    location: 'Lund, Sweden',
    deadline: '1 Jun 2026',
    link: '#'
  },
  {
    id: 3,
    category: 'Jobs',
    typeLabel: 'Job opportunity',
    tagClass: 'tag-job',
    uniShort: 'UU',
    university: 'Uppsala University',
    title: 'Research assistant — Computational Biology department',
    duration: 'Full-time · Permanent',
    location: 'Uppsala, Sweden',
    deadline: 'Open until filled',
    link: '#'
  },
  {
    id: 4,
    category: 'Courses',
    typeLabel: 'Course',
    tagClass: 'tag-course',
    uniShort: 'CTH',
    university: 'Chalmers University',
    title: 'Advanced Machine Learning — Spring 2026 open enrolment',
    duration: '7.5 credits · Semester',
    location: 'Gothenburg / Online',
    deadline: '20 May 2026',
    link: '#'
  },
  {
    id: 5,
    category: 'Thesis',
    typeLabel: 'Master thesis',
    tagClass: 'tag-thesis',
    uniShort: 'LiU',
    university: 'Linköping University',
    title: 'Human-computer interaction in mixed-reality environments',
    duration: 'Full-time · 6 months',
    location: 'Linköping, Sweden',
    deadline: '30 Apr 2026',
    link: '#'
  },
  {
    id: 6,
    category: 'Internship',
    typeLabel: 'Internship',
    tagClass: 'tag-intern',
    uniShort: 'SU',
    university: 'Stockholm University',
    title: 'Digital marketing & communications intern — Business School',
    duration: 'Part-time · 4 months',
    location: 'Stockholm, Sweden',
    deadline: '10 Jun 2026',
    link: '#'
  }
];

export function applyFilters(data, { query, uni, cat }) {
  return data.filter(item => {
    const matchesSearch = !query || item.title.toLowerCase().includes(query.toLowerCase());
    const matchesUni = uni === 'All universities' || item.university.includes(uni) || item.uniShort === uni;
    const matchesCat = cat === 'All' || item.category === cat;
    return matchesSearch && matchesUni && matchesCat;
  });
}