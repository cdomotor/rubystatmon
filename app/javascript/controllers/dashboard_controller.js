// File: app/javascript/controllers/dashboard_controller.js
// Renders charts and handles "Mark reviewed" + per-station sparklines.

import { Controller } from "@hotwired/stimulus"
import Chart from "chart.js/auto"

export default class extends Controller {
  static targets = ["latencyChart", "healthChart"]

  connect() {
    this.csrf = document.querySelector('meta[name="csrf-token"]')?.content
    this.renderLatencyChart()
    this.renderHealthChart()
    this.renderAllSparklines()
  }

  // ----- Big charts -----
  async renderLatencyChart() {
    const res = await fetch("/dashboard/metrics/latency")
    if (!res.ok) return
    const data = await res.json()
    const labels = data.map(d => d.date)
    const values = data.map(d => d.value)

    const ctx = this.latencyChartTarget.getContext("2d")
    new Chart(ctx, {
      type: "line",
      data: { labels, datasets: [{ label: "Avg Ping (ms)", data: values }] },
      options: {
        responsive: true,
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: true } }
      }
    })
  }

  async renderHealthChart() {
    const res = await fetch("/dashboard/metrics/health")
    if (!res.ok) return
    const data = await res.json()
    const labels = data.map(d => d.date)
    const values = data.map(d => d.value)

    const ctx = this.healthChartTarget.getContext("2d")
    new Chart(ctx, {
      type: "line",
      data: { labels, datasets: [{ label: "% Unhealthy", data: values }] },
      options: {
        responsive: true,
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: true, max: 100 } }
      }
    })
  }

  // ----- Sparklines (24h per station) -----
  async renderAllSparklines() {
    const nodes = document.querySelectorAll("canvas[data-sparkline-id]")
    nodes.forEach(async (canvas) => {
      const id = canvas.getAttribute("data-sparkline-id")
      const res = await fetch(`/dashboard/metrics/stations/${id}/latency24h`)
      if (!res.ok) return
      const data = await res.json()
      const labels = data.map(d => d.ts)
      const values = data.map(d => d.value)

      const ctx = canvas.getContext("2d")
      new Chart(ctx, {
        type: "line",
        data: { labels, datasets: [{ data: values, label: "24h", fill: false }] },
        options: {
          responsive: true,
          elements: { point: { radius: 0 } },
          plugins: { legend: { display: false }, tooltip: { enabled: true } },
          scales: {
            x: { display: false },
            y: { display: false, beginAtZero: true }
          }
        }
      })
    })
  }

  // ----- Mark reviewed -----
  async markReviewed(event) {
    const stationId = event.params.stationId
    const btn = event.currentTarget
    btn.disabled = true

    const res = await fetch(`/dashboard/spotlight/${stationId}/mark_reviewed`, {
      method: "POST",
      headers: { "X-CSRF-Token": this.csrf, "Accept": "application/json" }
    })

    if (res.ok) {
      const card = document.getElementById(`spotlight_${stationId}`)
      card?.classList.add("opacity-60")
      setTimeout(() => card?.remove(), 150)
    } else {
      btn.disabled = false
      alert("Failed to mark reviewed")
    }
  }
}
