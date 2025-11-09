(function () {
  const totals = (window.TrackYourSheets && window.TrackYourSheets.premiumTotals) || {};
  const chartCanvas = document.getElementById('premiumChart');
  if (!chartCanvas || typeof Chart === 'undefined') {
    return;
  }

  const labels = {
    all: 'All time',
    today: 'Today',
    week: 'This week',
    month: 'This month',
    quarter: 'This quarter',
    year: 'Year to date',
  };
  const rangeOrder = ['all', 'today', 'week', 'month', 'quarter', 'year'];
  const currency = chartCanvas.dataset.premiumCurrency || 'USD';
  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  });

  const getValue = (key) => {
    const raw = totals[key];
    const parsed = Number.parseFloat(raw ?? 0);
    return Number.isNaN(parsed) ? 0 : parsed;
  };

  function buildData(activeRange) {
    if (activeRange === 'all') {
      return rangeOrder.map((key) => ({
        key,
        label: labels[key],
        value: getValue(key),
        isActive: key === 'all',
      }));
    }
    return [
      {
        key: activeRange,
        label: labels[activeRange],
        value: getValue(activeRange),
        isActive: true,
      },
    ];
  }

  const context = chartCanvas.getContext('2d');
  let activeRange = 'all';
  let currentDataset = buildData(activeRange);

  const chart = new Chart(context, {
    type: 'bar',
    data: {
      labels: currentDataset.map((entry) => entry.label),
      datasets: [
        {
          label: 'Premium collected',
          data: currentDataset.map((entry) => entry.value),
          backgroundColor: currentDataset.map((entry) =>
            entry.isActive ? 'rgba(13, 110, 253, 0.8)' : 'rgba(206, 212, 218, 0.6)'
          ),
          borderRadius: 6,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y || 0;
              return `${formatter.format(value)} collected`;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback(value) {
              return formatter.format(value);
            },
          },
        },
      },
    },
  });

  const summaryEl = document.querySelector('[data-premium-summary]');

  function updateSummary(range) {
    if (!summaryEl) {
      return;
    }
    const value = getValue(range);
    const label = labels[range] || 'Total';
    summaryEl.textContent = `${label} · ${formatter.format(value)} collected`;
  }

  function applyFilter(range) {
    activeRange = range;
    currentDataset = buildData(activeRange);
    chart.data.labels = currentDataset.map((entry) => entry.label);
    chart.data.datasets[0].data = currentDataset.map((entry) => entry.value);
    chart.data.datasets[0].backgroundColor = currentDataset.map((entry) =>
      entry.isActive ? 'rgba(13, 110, 253, 0.8)' : 'rgba(206, 212, 218, 0.6)'
    );
    chart.update();
    updateSummary(range);
  }

  document.querySelectorAll('[data-premium-range]').forEach((button) => {
    button.addEventListener('click', () => {
      const range = button.getAttribute('data-premium-range');
      if (!range || range === activeRange) {
        return;
      }
      document.querySelectorAll('[data-premium-range]').forEach((btn) =>
        btn.classList.toggle('active', btn === button)
      );
      applyFilter(range);
    });
  });
})();
