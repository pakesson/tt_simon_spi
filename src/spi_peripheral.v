`default_nettype none

module spi_peripheral (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       spi_sck,
    input  wire       spi_mosi,
    input  wire       spi_cs_n,
    output reg        spi_miso,
    output reg        cmd_valid,
    output reg        rx_byte_valid,
    output wire [7:0] rx_shift_out,
    input  wire [7:0] tx_byte,
    input  wire       tx_byte_load
);

  reg [2:0] sck_sync;
  reg [2:0] cs_sync;
  reg [1:0] mosi_sync;

  reg [7:0] rx_shift;
  reg [7:0] tx_shift;
  reg [2:0] bit_cnt;
  reg       got_cmd;

  wire sck_rise   = (sck_sync[2:1] == 2'b01);
  wire sck_fall   = (sck_sync[2:1] == 2'b10);
  wire cs_active  = ~cs_sync[2];
  wire cs_start   = (cs_sync[2:1] == 2'b10);
  wire cs_end     = (cs_sync[2:1] == 2'b01);
  wire mosi_stable = mosi_sync[1];

  assign rx_shift_out = rx_shift;

  always @(posedge clk) begin
    if (!rst_n) begin
      sck_sync      <= 3'b000;
      cs_sync       <= 3'b111;
      mosi_sync     <= 2'b00;
      rx_shift      <= 8'd0;
      tx_shift      <= 8'd0;
      bit_cnt       <= 3'd0;
      got_cmd       <= 1'b0;
      spi_miso      <= 1'b0;
      cmd_valid     <= 1'b0;
      rx_byte_valid <= 1'b0;
    end else begin
      sck_sync      <= {sck_sync[1:0], spi_sck};
      cs_sync       <= {cs_sync[1:0], spi_cs_n};
      mosi_sync     <= {mosi_sync[0], spi_mosi};
      cmd_valid     <= 1'b0;
      rx_byte_valid <= 1'b0;

      if (cs_start) begin
        bit_cnt  <= 3'd0;
        got_cmd  <= 1'b0;
        rx_shift <= 8'd0;
        tx_shift <= tx_byte;
      end

      if (cs_active && sck_rise) begin
        rx_shift <= {rx_shift[6:0], mosi_stable};
        if (bit_cnt == 3'd7) begin
          bit_cnt <= 3'd0;
          if (!got_cmd) begin
            cmd_valid <= 1'b1;
            got_cmd   <= 1'b1;
          end else begin
            rx_byte_valid <= 1'b1;
          end
        end else begin
          bit_cnt <= bit_cnt + 3'd1;
        end
      end

      if (cs_active && sck_fall) begin
        spi_miso <= tx_shift[7];
        tx_shift <= {tx_shift[6:0], 1'b0};
      end

      if (tx_byte_load) begin
        tx_shift <= tx_byte;
      end

      if (cs_end) begin
        got_cmd <= 1'b0;
      end
    end
  end

endmodule
