# File: app/models/station.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/models/station.rb

class Station < ApplicationRecord
  # Fix the deprecation warning — use keyword arg for coder:
  # old: serialize :configured_parameters, JSON
  serialize :configured_parameters, coder: JSON

  has_many :readings, dependent: :destroy
  has_many :ping_results, dependent: :destroy

  # Return an array of [timestamp, value] for a given parameter
  def series_for(param, since: 24.hours.ago)
    # Be defensive during setup/migrations
    return [] unless ActiveRecord::Base.connection.data_source_exists?('readings')

    readings
      .where(parameter: param)
      .where('taken_at >= ?', since)
      .order(:taken_at)
      .pluck(:taken_at, :value)
  end
end
