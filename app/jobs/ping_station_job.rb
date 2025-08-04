class PingStationJob < ApplicationJob
  queue_as :default

  def perform(station_id)
    station = Station.find(station_id)
    result = `ping -n 1 \#{station.ip_address}`
    success = result.include?("TTL=")
    latency = result[/time=(\d+)ms/, 1]&.to_i

    station.ping_result.create!(
      success: success,
      latency_ms: latency,
      timestamp: Time.now
    )
  end
end
