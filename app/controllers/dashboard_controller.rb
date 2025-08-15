# File: app/controllers/dashboard_controller.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/controllers/dashboard_controller.rb

class DashboardController < ApplicationController
  def index
    @summary = {}

    stations_ready = ActiveRecord::Base.connection.data_source_exists?('stations')
    pings_ready    = ActiveRecord::Base.connection.data_source_exists?('ping_results')
    reads_ready    = ActiveRecord::Base.connection.data_source_exists?('readings')

    if stations_ready
      @summary["Stations"] = Station.count
    end

    if pings_ready
      @summary["Pings (24h)"] = PingResult.where('created_at >= ?', 24.hours.ago).count
      @summary["Last Ping"]   = PingResult.order(created_at: :desc).limit(1).pick(:created_at)&.in_time_zone&.strftime("%Y-%m-%d %H:%M")
    end

    if reads_ready
      @summary["Readings (24h)"] = Reading.where('taken_at >= ?', 24.hours.ago).count
    end

    # Always provide something so the view can render
    @summary = {
      "Stations"       => @summary["Stations"] || 0,
      "Pings (24h)"    => @summary["Pings (24h)"] || 0,
      "Readings (24h)" => @summary["Readings (24h)"] || 0,
      "Last Ping"      => @summary["Last Ping"] || "—"
    }
  end
end
