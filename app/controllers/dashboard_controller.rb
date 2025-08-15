# File: app/controllers/dashboard_controller.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/controllers/dashboard_controller.rb

class DashboardController < ApplicationController
  def index
    # --- Summary (already working for you) ---
    @summary = {
      "Stations"       => table?(:stations)     ? Station.count : 0,
      "Pings (24h)"    => table?(:ping_results) ? PingResult.where('created_at >= ?', 24.hours.ago).count : 0,
      "Readings (24h)" => table?(:readings)     ? Reading.where('taken_at >= ?', 24.hours.ago).count : 0,
      "Last Ping"      => table?(:ping_results) ? PingResult.order(created_at: :desc).limit(1).pick(:created_at)&.in_time_zone&.strftime("%Y-%m-%d %H:%M") : "—"
    }

    # --- Always initialize to an array so the view can .any? safely ---
    @flagged_stations = []

    # Defensive: only compute flags if tables exist
    return unless table?(:stations) && table?(:ping_results)

    cutoff = 24.hours.ago

    Station.includes(:ping_results).find_each do |s|
      last_ping_at     = s.ping_results.maximum(:created_at)
      recent_failures  = s.ping_results.where('created_at >= ?', 6.hours.ago).where(success: false).count
      stale            = last_ping_at.nil? || last_ping_at < cutoff
      too_many_failures = recent_failures >= 3

      if stale || too_many_failures
        @flagged_stations << {
          station: s,
          last_ping_at: last_ping_at,
          recent_failures: recent_failures,
          reason: [stale ? "stale (>24h)" : nil, too_many_failures ? "failures (≥3 in 6h)" : nil].compact.join(", ")
        }
      end
    end
  end

  private

  def table?(name)
    ActiveRecord::Base.connection.data_source_exists?(name.to_s)
  end
end
