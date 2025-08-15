# File: app/controllers/dashboard_controller.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/controllers/dashboard_controller.rb

class DashboardController < ApplicationController
  def index
    # ---- Summary (kept defensive) ----
    @summary = {
      "Stations"       => table?(:stations)     ? Station.count : 0,
      "Pings (24h)"    => table?(:ping_results) ? PingResult.where('created_at >= ?', 24.hours.ago).count : 0,
      "Readings (24h)" => table?(:readings)     ? Reading.where('taken_at >= ?', 24.hours.ago).count : 0,
      "Last Ping"      => table?(:ping_results) ? PingResult.order(created_at: :desc).limit(1).pick(:created_at)&.in_time_zone&.strftime("%Y-%m-%d %H:%M") : "—"
    }

    # Always provide arrays so views can safely call .any?/.each
    @flagged_stations  = []
    @random_spotlight  = []

    return unless table?(:stations)

    # ---- Station Spotlight (3 random) ----
    random_sql = case ActiveRecord::Base.connection.adapter_name
                 when /sqlite/i, /postgres/i then 'RANDOM()'
                 else 'RAND()' # MySQL / MariaDB
                 end
    @random_spotlight = Station.order(Arel.sql(random_sql)).limit(3).to_a

    # ---- Flagged stations (bulk, no N+1) ----
    return unless table?(:ping_results)

    cutoff_24h = 24.hours.ago

    # 1) Last ping per station (single query)
    last_ping_map = PingResult.group(:station_id).maximum(:created_at)
    # 2) Recent failure counts (single query)
    recent_failures = PingResult.where('created_at >= ?', 6.hours.ago)
                                .where(success: false)
                                .group(:station_id).count

    Station.find_each do |s|
      last_at = last_ping_map[s.id]
      fails   = recent_failures[s.id].to_i
      stale   = last_at.nil? || last_at < cutoff_24h

      next unless stale || fails >= 3

      @flagged_stations << {
        station: s,
        last_ping_at: last_at,
        recent_failures: fails,
        reason: [stale ? "stale (>24h)" : nil, fails >= 3 ? "failures (≥3 in 6h)" : nil].compact.join(", ")
      }
    end
  end

  private

  def table?(name)
    ActiveRecord::Base.connection.data_source_exists?(name.to_s)
  end
end
