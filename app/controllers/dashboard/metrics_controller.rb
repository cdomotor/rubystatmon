# File: app/controllers/dashboard/metrics_controller.rb
class Dashboard::MetricsController < ApplicationController
  def latency
    data = Rails.cache.fetch("metrics:latency:14d", expires_in: 60.seconds) do
      DashboardService.latency_timeseries(days: 14)
    end
    render json: data
  end

  def health
    data = Rails.cache.fetch("metrics:health:14d", expires_in: 60.seconds) do
      DashboardService.health_timeseries(days: 14)
    end
    render json: data
  end

  def station_latency_24h
    id = params[:id].to_i
    data = Rails.cache.fetch("metrics:station:#{id}:latency24h", expires_in: 60.seconds) do
      DashboardService.station_latency_24h(id)
    end
    render json: data
  end
end
