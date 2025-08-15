# File: app/models/station.rb
# Full path: /app/models/station.rb

class Station < ApplicationRecord
  # If you're on SQLite, serialize JSON into a text column transparently.
  serialize :configured_parameters, JSON

  has_many :readings, dependent: :nullify
  has_many :ping_results, dependent: :destroy

  # Fallback list if a station has no custom config yet.
  # Adjust to your domain defaults.
  DEFAULT_PARAMETER_LIST = %w[Battery flow_rate turbidity SignalStrength].freeze

  def selected_parameters
    Array(configured_parameters).presence || DEFAULT_PARAMETER_LIST
  end

  # Optional helper to fetch timeseries (minimizes controller clutter)
  # Expects Reading model with columns: station_id, parameter, timestamp, value
  def series_for(param, since: 7.days.ago)
    readings.where(parameter: param)
            .where('timestamp >= ?', since)
            .order(:timestamp)
            .pluck(:timestamp, :value)
  end
end
# == Schema Information
#
# Table name: stations      