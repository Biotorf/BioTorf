<script setup>
import { computed } from 'vue';
import { useDbStore } from '@/stores/db';
import { useUiStore } from '@/stores/ui';
import { usePermissions } from '@/composables/usePermissions';
import { useFormatters } from '@/composables/useFormatters';
import StatusPill from '@/components/ui/StatusPill.vue';

const db = useDbStore();
const ui = useUiStore();
const { canSeeFarm } = usePermissions();
const { num, day } = useFormatters();

const farms = computed(() =>
  db.farms
    .filter(canSeeFarm)
    .filter((f) => {
      const q = ui.search.toLowerCase();
      if (!q) return true;
      return [f.name, f.region, f.crop, f.owner, f.status]
        .join(' ').toLowerCase().includes(q);
    })
);

const commsCount = (farmId) => db.comms.filter((c) => c.farmId === farmId).length;
const commsUnread = (farmId) => db.comms.filter((c) => c.farmId === farmId && !c.read).length;
</script>

<template>
  <div>
    <div class="pagehead">
      <div>
        <h1>Клиенты и хозяйства</h1>
        <div class="subtitle">Единый реестр хозяйств и контактов</div>
      </div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Клиент / хозяйство</th>
            <th>Регион</th>
            <th>Культура</th>
            <th>Площадь</th>
            <th>Менеджер</th>
            <th>Статус</th>
            <th>След. контакт</th>
            <th>Связь</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="f in farms"
            :key="f.id"
            class="clickrow"
            @click="ui.openClient(f.id)"
          >
            <td>
              <span class="txt-link">{{ f.name }}</span>
              <div class="mini">{{ f.type }} · {{ f.id }}</div>
            </td>
            <td>{{ f.region }}</td>
            <td>{{ f.crop }}</td>
            <td>{{ num(f.area) }} га</td>
            <td>{{ f.owner }}</td>
            <td><StatusPill :status="f.status" /></td>
            <td>{{ day(f.next) }}</td>
            <td @click.stop>
              <button class="btn slim ghost" title="Открыть переписку и звонки" @click="ui.openComms(f.id)">
                ☎ {{ commsCount(f.id) }}<template v-if="commsUnread(f.id)"> · <span class="pill red">{{ commsUnread(f.id) }}</span></template>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>