# File: app/models/station.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/models/station.rb

class Station < ApplicationRecord
  # Use keyword arg for coder to silence the Rails 7.2 deprecation
  serialize :configured_parameters, coder: JSON

  has_many :ping_results, dependent: :destroy
  has_many :readings,     dependent: :destroy

  # --- Health policy (tweak as you like) ---
  STALE_CUTOFF_HOURS = 24
  FAIL_WINDOW_HOURS  = 6
  FAIL_LIMIT         = 3

  # Last time we saw any ping for this station
  def last_ping_at
    return nil unless data_source?(:ping_results)
    @last_ping_at ||= ping_results.maximum(:created_at)
  end

  # Count of failed pings within a window (default 6h)
  def recent_failures_count(window_hours: FAIL_WINDOW_HOURS)
    return 0 unless data_source?(:ping_results)
    ping_results
      .where('created_at >= ?', window_hours.hours.ago)
      .where(success: false)
      .count
  end

  # Consider the station stale if last ping older than 24h (or never)
  def stale?
    lp = last_ping_at
    lp.nil? || lp < STALE_CUTOFF_HOURS.hours.ago
  end

  # Our simple health rule: stale OR too many recent failures
  def unhealthy?
    stale? || recent_failures_count >= FAIL_LIMIT
  end

  private

  def data_source?(name)
    ActiveRecord::Base.connection.data_source_exists?(name.to_s)
  end
end
