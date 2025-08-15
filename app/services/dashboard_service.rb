# File: app/services/dashboard_service.rb
class DashboardService
  class << self
    def system_summary(stations)
      {
        "Total Stations" => stations.count,
        "Online" => stations.count(&:online?),
        "Offline" => stations.reject(&:online?).count,
        "Avg Ping (ms)" => average_ping(stations)
      }
    end

    def flagged_stations(stations)
      stations.select(&:unhealthy?)
    end

    def random_spotlight(stations, count: 3)
      pool = stations.sort_by { |s| s.last_viewed_at || Time.at(0) }
      pool.first(count)
    end

    # ===== Charts: JSON =====

    # [{date: "YYYY-MM-DD", value: Float}]
    def latency_timeseries(days: 14)
      from = days.days.ago.beginning_of_day
      pings = PingResult.where("created_at >= ?", from)
                        .group("DATE(created_at)")
                        .average(:latency_ms)
      fill_series(from, days) { |date| pings[date] || 0 }
    end

    # [{date: "YYYY-MM-DD", value: Float(%)}]
    def health_timeseries(days: 14)
      from = days.days.ago.beginning_of_day
      dates = (0..days).map { |i| (from.to_date + i.days) }
      stations = Station.all.to_a

      dates.map do |d|
        unhealthy = stations.count { |s| unhealthy_on_date?(s, d) }
        pct = stations.any? ? ((unhealthy.to_f / stations.size) * 100.0).round(1) : 0
        { date: d.to_s, value: pct }
      end
    end

    # Mini sparkline (last 24h): [{ts: "HH:MM", value: ms}]
    def station_latency_24h(station_id)
      from = 24.hours.ago
      rows = PingResult.where(station_id: station_id)
                       .where("created_at >= ?", from)
                       .order(:created_at)
                       .pluck(:created_at, :latency_ms)
      rows.map { |ts, v| { ts: ts.strftime("%H:%M"), value: v || 0 } }
    end

    private

    def unhealthy_on_date?(station, date)
      last_ping = station.ping_results.where("DATE(created_at)=?", date).order(created_at: :desc).first
      lat_bad = last_ping&.latency_ms && (last_ping.latency_ms > (station.latency_threshold_ms || 3000))
      lat_bad || false
    end

    def average_ping(stations)
      vals = stations.map { |s| s.ping_results.last&.latency_ms }.compact
      return "N/A" if vals.empty?
      (vals.sum.to_f / vals.size).round(1)
    end

    def fill_series(from, days)
      (0..days).map do |i|
        d = (from.to_date + i.days)
        { date: d.to_s, value: yield(d) }
      end
    end
  end
end
