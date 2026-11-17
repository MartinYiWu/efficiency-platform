<script setup lang="ts">
defineProps<{ title?: string; description?: string }>();
</script>
<template>
  <section class="ui-page">
    <header v-if="title || description" class="ui-header">
      <div>
        <h1 v-if="title">{{ title }}</h1>
        <p v-if="description">{{ description }}</p>
      </div>
      <slot name="extra" />
    </header>
    <slot />
  </section>
</template>
