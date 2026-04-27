/*
 * Copyright (c) 2026 Philip Åkesson
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_pakesson_simon64_128 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  reg [1:0] rst_pipe;
  wire rst_n_int = rst_pipe[1];

  localparam [7:0] CMD_WRITE_KEY_128  = 8'h10;
  localparam [7:0] CMD_WRITE_BLOCK_64 = 8'h20;
  localparam [7:0] CMD_START_ENCRYPT  = 8'h30;
  localparam [7:0] CMD_START_DECRYPT  = 8'h31;
  localparam [7:0] CMD_READ_BLOCK_64  = 8'h40;
  localparam [7:0] CMD_READ_STATUS    = 8'h50;

  localparam [1:0] PL_NONE  = 2'd0;
  localparam [1:0] PL_KEY   = 2'd1;
  localparam [1:0] PL_BLOCK = 2'd2;

  wire spi_sck  = ui_in[0];
  wire spi_mosi = ui_in[1];
  wire spi_cs_n = ui_in[2];

  wire        spi_cmd_valid;
  wire        spi_rx_byte_valid;
  wire [7:0]  spi_rx_shift;
  reg  [7:0]  spi_tx_byte;
  reg         spi_tx_byte_load;
  wire        spi_miso;

  reg [1:0]  payload_mode;
  reg [4:0]  byte_cnt;

  reg         core_start_pipe;
  reg         core_decrypt_pipe;
  reg         out_valid;

  wire core_busy;
  wire core_done;
  wire [63:0] core_block_out;

  spi_peripheral spi_p (
      .clk(clk),
      .rst_n(rst_n_int),
      .spi_sck(spi_sck),
      .spi_mosi(spi_mosi),
      .spi_cs_n(spi_cs_n),
      .spi_miso(spi_miso),
      .cmd_valid(spi_cmd_valid),
      .rx_byte_valid(spi_rx_byte_valid),
      .rx_shift_out(spi_rx_shift),
      .tx_byte(spi_tx_byte),
      .tx_byte_load(spi_tx_byte_load)
  );

  simon64_128_core core (
      .clk(clk),
      .rst_n(rst_n_int),
      .start(core_start_pipe),
      .decrypt(core_decrypt_pipe),
      .key_byte_valid(spi_rx_byte_valid && (payload_mode == PL_KEY) && (byte_cnt != 5'd0)),
      .key_byte(spi_rx_shift),
      .block_byte_valid(spi_rx_byte_valid && (payload_mode == PL_BLOCK) && (byte_cnt != 5'd0)),
      .block_byte(spi_rx_shift),
      .busy(core_busy),
      .done(core_done),
      .block_out(core_block_out)
  );

  assign uo_out[0] = spi_miso;
  assign uo_out[1] = core_busy;
  assign uo_out[2] = out_valid;
  assign uo_out[3] = 1'b0;
  assign uo_out[4] = 1'b0;
  assign uo_out[5] = 1'b0;
  assign uo_out[6] = 1'b0;
  assign uo_out[7] = 1'b0;

  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rst_pipe <= 2'b00;
    end else begin
      rst_pipe <= {rst_pipe[0], 1'b1};
    end
  end

  always @(posedge clk) begin
    if (!rst_n_int) begin
      payload_mode      <= PL_NONE;
      byte_cnt          <= 5'd0;
      spi_tx_byte       <= 8'h00;
      spi_tx_byte_load  <= 1'b0;
      core_start_pipe   <= 1'b0;
      core_decrypt_pipe <= 1'b0;
      out_valid         <= 1'b0;
    end else begin
      spi_tx_byte_load <= 1'b0;
      core_start_pipe  <= 1'b0;

      if (core_done) begin
        out_valid <= 1'b1;
      end

      if (spi_cmd_valid) begin
        payload_mode <= PL_NONE;
        byte_cnt     <= 5'd0;

        case (spi_rx_shift)
          CMD_WRITE_KEY_128: begin
            if (!core_busy) begin
              payload_mode <= PL_KEY;
              byte_cnt     <= 5'd16;
            end
          end

          CMD_WRITE_BLOCK_64: begin
            if (!core_busy) begin
              payload_mode <= PL_BLOCK;
              byte_cnt     <= 5'd8;
              out_valid    <= 1'b0;
            end
          end

          CMD_START_ENCRYPT: begin
            if (!core_busy) begin
              core_start_pipe   <= 1'b1;
              core_decrypt_pipe <= 1'b0;
              out_valid         <= 1'b0;
            end
          end

          CMD_START_DECRYPT: begin
            if (!core_busy) begin
              core_start_pipe   <= 1'b1;
              core_decrypt_pipe <= 1'b1;
              out_valid         <= 1'b0;
            end
          end

          CMD_READ_BLOCK_64: begin
            if (out_valid && !core_busy) begin
              spi_tx_byte      <= core_block_out[63:56];
              spi_tx_byte_load <= 1'b1;
              byte_cnt         <= 5'd1;
            end
          end

          CMD_READ_STATUS: begin
            spi_tx_byte      <= {5'b00000, out_valid, core_busy, 1'b0};
            spi_tx_byte_load <= 1'b1;
          end

          default: begin
          end
        endcase
      end

      if (spi_rx_byte_valid && (payload_mode != PL_NONE) && (byte_cnt != 5'd0)) begin
        byte_cnt <= byte_cnt - 5'd1;
        if (byte_cnt == 5'd1) begin
          payload_mode <= PL_NONE;
        end
      end

      if (spi_rx_byte_valid && (payload_mode == PL_NONE) && (byte_cnt != 5'd0) && (byte_cnt < 5'd8)) begin
        case (byte_cnt)
          5'd1: spi_tx_byte <= core_block_out[55:48];
          5'd2: spi_tx_byte <= core_block_out[47:40];
          5'd3: spi_tx_byte <= core_block_out[39:32];
          5'd4: spi_tx_byte <= core_block_out[31:24];
          5'd5: spi_tx_byte <= core_block_out[23:16];
          5'd6: spi_tx_byte <= core_block_out[15:8];
          5'd7: spi_tx_byte <= core_block_out[7:0];
          default: spi_tx_byte <= 8'h00;
        endcase
        spi_tx_byte_load <= 1'b1;
        byte_cnt         <= byte_cnt + 5'd1;
      end
    end
  end

  wire _unused = &{ena, uio_in, 1'b0};

`ifdef USE_ART
  (* keep *)
  chip_art chip_art_instance();
`endif
endmodule
